"""Gmail integration: Google OAuth + inbox sync, using plain HTTPS calls (no Google SDK)."""
import os, re, json, time, base64, hmac, hashlib, html as _html
from email.message import EmailMessage
from email.utils import parseaddr
from urllib.parse import urlencode
import requests
from cryptography.fernet import Fernet
import db, email_assistant

SCOPE = "https://www.googleapis.com/auth/gmail.modify"  # read + labels + drafts + send (cannot permanently delete)
LABELS = {"replied": "SiteBot/Replied", "draft": "SiteBot/Draft ready", "attention": "SiteBot/Needs you"}
class GmailAuthError(Exception): pass

def env(k, d=""): return os.getenv(k, d)
def configured(): return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))
def _token_url(): return env("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
def _api(): return env("GMAIL_API_BASE", "https://gmail.googleapis.com/gmail/v1/users/me")

# ---- token encryption + signed OAuth state
def _fernet():
    k = env("TOKEN_KEY") or base64.urlsafe_b64encode(hashlib.sha256((env("GOOGLE_CLIENT_SECRET") + "|sitebot").encode()).digest()).decode()
    return Fernet(k)
def enc(s): return _fernet().encrypt(s.encode()).decode()
def dec(s): return _fernet().decrypt(s.encode()).decode()
def _sig(p): return hmac.new((env("GOOGLE_CLIENT_SECRET") + "|state").encode(), p.encode(), hashlib.sha256).hexdigest()
def make_state(bot_id, user_id):
    p = base64.urlsafe_b64encode(json.dumps({"b": bot_id, "u": user_id, "t": int(time.time())}).encode()).decode(); return p + "." + _sig(p)
def read_state(s):
    try:
        p, sig = s.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sig(p)): return None
        d = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        return d if time.time() - d["t"] < 900 else None
    except Exception: return None

# ---- OAuth
def auth_url(state, redirect):
    return env("GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth") + "?" + urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"), "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state})
def exchange(code, redirect):
    r = requests.post(_token_url(), data={"code": code, "client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
                      "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=20)
    r.raise_for_status(); return r.json()
def access_token(acc):
    r = requests.post(_token_url(), data={"client_id": env("GOOGLE_CLIENT_ID"), "client_secret": env("GOOGLE_CLIENT_SECRET"),
                      "refresh_token": dec(acc["refresh_token"]), "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200: raise GmailAuthError("Google rejected the saved connection (it expired or was revoked). Please reconnect Gmail.")
    return r.json()["access_token"]
def g(method, path, tok, **kw):
    r = requests.request(method, _api() + path, headers={"Authorization": "Bearer " + tok}, timeout=25, **kw)
    r.raise_for_status(); return r.json() if r.content else {}
def profile(tok): return g("GET", "/profile", tok)["emailAddress"]
def save_account(bot_id, email, refresh):
    db.run("delete from gmail_accounts where bot_id=?", (bot_id,))
    db.run("insert into gmail_accounts(bot_id,email,refresh_token) values(?,?,?)", (bot_id, email, enc(refresh)))
def disconnect(bot_id):
    acc = db.one("select * from gmail_accounts where bot_id=?", (bot_id,))
    if acc:
        try: requests.post(env("GOOGLE_REVOKE_URL", "https://oauth2.googleapis.com/revoke"), data={"token": dec(acc["refresh_token"])}, timeout=10)
        except Exception: pass
        db.run("delete from gmail_accounts where bot_id=?", (bot_id,))

# ---- reading mail
def _b64(d): return base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)).decode("utf-8", "ignore")
def _hdr(msg, name):
    for h in msg["payload"].get("headers", []):
        if h["name"].lower() == name.lower(): return h["value"]
    return ""
def _body(payload):
    plain, htm = [], []
    def walk(p):
        d = (p.get("body") or {}).get("data"); mt = p.get("mimeType", "")
        if d and mt == "text/plain": plain.append(_b64(d))
        elif d and mt == "text/html": htm.append(_b64(d))
        for x in p.get("parts") or []: walk(x)
    walk(payload)
    t = "\n".join(plain) or re.sub(r"<[^>]+>", " ", _html.unescape(re.sub(r"(?is)<(script|style).*?</\1>", " ", " ".join(htm))))
    t = re.split(r"\n\s*On .{0,120}wrote:|\n-{2,}\s*Original Message", t)[0]  # drop quoted history
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in t.splitlines() if not l.startswith(">"))).strip()
def automated(msg, sender):
    h = lambda n: _hdr(msg, n).lower().strip()
    return (h("auto-submitted") not in ("", "no") or h("precedence") in ("bulk", "list", "junk") or bool(_hdr(msg, "List-Unsubscribe") or _hdr(msg, "List-Id"))
            or bool(re.search(r"(no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|bounce)", sender, re.I))
            or bool(re.search(r"(out of office|automatic reply|auto-?reply|undeliverable)", _hdr(msg, "Subject"), re.I)))

# ---- writing mail
def footer(bot): return env("EMAIL_FOOTER", f"\n\n—\nThis reply was written by {bot['name']}'s AI assistant. If it didn't answer your question, just reply and a person will follow up.")
def build_reply(me, to, subject, body, msg_id, refs, thread, auto):
    clean = lambda s: re.sub(r"[\r\n]+", " ", s).strip()
    m = EmailMessage(); m["To"] = clean(to); m["From"] = me
    m["Subject"] = clean(subject) if re.match(r"(?i)\s*re:", subject) else "Re: " + clean(subject)
    if msg_id: m["In-Reply-To"] = clean(msg_id); m["References"] = clean((refs + " " + msg_id).strip())
    if auto: m["Auto-Submitted"] = "auto-replied"
    m.set_content(body)
    return {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode(), "threadId": thread}
def _labels(tok):
    have = {l["name"]: l["id"] for l in g("GET", "/labels", tok).get("labels", [])}; out = {}
    for k, n in LABELS.items():
        if n not in have:
            try: have[n] = g("POST", "/labels", tok, json={"name": n, "labelListVisibility": "labelShow", "messageListVisibility": "show"})["id"]
            except Exception: have[n] = None
        out[k] = have[n]
    return out

def sync(bot, max_msgs=5, budget=45):
    """Reads new unread mail, classifies it, and drafts/sends replies. Returns counts."""
    acc = db.one("select * from gmail_accounts where bot_id=?", (bot["id"],))
    if not acc: raise GmailAuthError("Gmail is not connected")
    t0, tok, me = time.time(), access_token(acc), acc["email"]; L = None
    res = dict(checked=0, drafts=0, sent=0, escalated=0, skipped=0, errors=0)
    ids = [m["id"] for m in g("GET", "/messages", tok, params={"q": f"in:inbox is:unread newer_than:2d -from:{me}", "maxResults": 15}).get("messages", [])]
    for mid in ids:
        if res["checked"] >= max_msgs or time.time() - t0 > budget: break
        if db.one("select id from emails where bot_id=? and gmail_id=?", (bot["id"], mid)): continue
        res["checked"] += 1
        try:
            L = L or _labels(tok); _process(bot, tok, me, mid, res, L)
        except Exception as e:
            print("gmail process failed:", e); res["errors"] += 1
            db.run("insert into emails(bot_id,sender,subject,body,category,reason,status,gmail_id,ts) values(?,?,?,?,?,?,?,?,?)", (bot["id"], "", "(could not process)", "", "review", str(e)[:200], "error", mid, int(time.time())))
    db.run("update gmail_accounts set last_sync=? where bot_id=?", (int(time.time()), bot["id"]))
    return res

def _process(bot, tok, me, mid, res, L):
    msg = g("GET", "/messages/" + mid, tok, params={"format": "full"}); now = int(time.time())
    raw_from = _hdr(msg, "From"); name, addr = parseaddr(raw_from); subject = _hdr(msg, "Subject") or "(no subject)"
    body = _body(msg["payload"])[:4000]; thread = msg.get("threadId")
    if not addr or addr.lower() == me.lower() or automated(msg, raw_from):
        db.run("insert into emails(bot_id,sender,subject,body,category,reason,status,gmail_id,thread_id,ts) values(?,?,?,?,?,?,?,?,?,?)",
               (bot["id"], addr or raw_from, subject, body, "skipped", "Automated or own message", "skipped", mid, thread, now)); res["skipped"] += 1; return
    r = email_assistant.handle(bot, addr, subject, body, name=name, meta={"gmail_id": mid, "thread_id": thread}); add, status, draft_id = [], r["status"], None
    if r["category"] == "routine" and r["reply"]:
        text = r["reply"] + footer(bot)
        recent = db.one("select count(*) n from emails where bot_id=? and sender=? and status=? and ts>?", (bot["id"], addr, "auto_sent", now - 86400))["n"]
        today = db.one("select count(*) n from emails where bot_id=? and status=? and ts>?", (bot["id"], "auto_sent", now - 86400))["n"]
        auto = bot["email_mode"] == "auto" and not recent and today < int(env("GMAIL_DAILY_AUTO_LIMIT", "30"))  # loop/spam guards
        payload = build_reply(me, addr, subject, text, _hdr(msg, "Message-ID"), _hdr(msg, "References"), thread, auto)
        if auto: g("POST", "/messages/send", tok, json=payload); status = "auto_sent"; add = [L["replied"]]; res["sent"] += 1
        else: draft_id = g("POST", "/drafts", tok, json={"message": payload})["id"]; status = "draft_saved"; add = [L["draft"]]; res["drafts"] += 1
        db.run("update emails set reply=? where id=?", (text, r["id"]))
    else: status = "escalated" if r["category"] == "urgent" else "needs_human"; add = [L["attention"]]; res["escalated"] += 1
    db.run("update emails set status=?, draft_id=? where id=?", (status, draft_id, r["id"]))
    add = [a for a in add if a]
    if add: g("POST", f"/messages/{mid}/modify", tok, json={"addLabelIds": add})

def draft_action(bot, email_row, send):
    """Owner approves (send) or discards a saved Gmail draft."""
    acc = db.one("select * from gmail_accounts where bot_id=?", (bot["id"],))
    if not acc or not email_row.get("draft_id"): raise GmailAuthError("No Gmail draft found for this email")
    tok = access_token(acc)
    if send: g("POST", "/drafts/send", tok, json={"id": email_row["draft_id"]})
    else: g("DELETE", "/drafts/" + email_row["draft_id"], tok)
    db.run("update emails set status=? where id=?", ("sent_by_owner" if send else "discarded", email_row["id"]))
