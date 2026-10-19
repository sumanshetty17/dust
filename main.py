import os, io, re, time, hashlib, hmac, secrets, requests
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
import html
from rag import urlparse, urljoin  # crash-proof versions
import db, rag, embed, llm, insights, email_assistant, gmail, reader_client, reader_client

try: db.init()
except Exception as e: print('DB init failed:', e)
DAILY_LIMIT = int(os.getenv('DAILY_CHAT_LIMIT', '0')); MAX_BOTS = int(os.getenv('MAX_BOTS_PER_USER', '0'))  # 0 = unlimited (free for now; set both later for paid plans)
app = FastAPI(title="SiteBot")
@app.exception_handler(Exception)
async def _unhandled(request, exc):  # never answer with plain text: the dashboard needs JSON, and the traceback goes to the Vercel logs
    import traceback; traceback.print_exc()
    return JSONResponse({"detail": "Something went wrong on our side. Please try again. If it keeps happening, check the Vercel logs for the cause."}, status_code=500)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
HERE = os.path.dirname(__file__)

def _hash(pw, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
def _check(pw, stored):
    return hmac.compare_digest(_hash(pw, stored.split("$")[0]), stored)

def current_user(authorization: str = Header("")):
    u = db.one("select * from users where token=?", (authorization.replace("Bearer ", ""),)) if authorization else None
    if not u: raise HTTPException(401, "Not logged in")
    return u
def own_bot(bot_id: int, u=Depends(current_user)):
    b = db.one("select * from bots where id=? and user_id=?", (bot_id, u["id"]))
    if not b: raise HTTPException(404, "Bot not found")
    return b

def _host(u):
    try: return (urlparse(u).hostname or "").lower().removeprefix("www.")
    except Exception: return ""
def _ip(request):
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "x")
def _allowed(b, request):
    """Website lock: when on, the chat only answers requests coming from the owner's own domain(s)."""
    if not b.get("domain_lock"): return True
    h = _host(request.headers.get("origin") or request.headers.get("referer") or "")
    if not h: return False
    ok = {_host(_url(b["site_url"])) if b["site_url"] else ""} | {d for d in (b.get("allowed_domains") or "").split(",") if d}
    ok.add((request.headers.get("host") or "").split(":")[0].lower().removeprefix("www."))  # platform's own pages: dashboard test, /demo
    return any(h == d or h.endswith("." + d) for d in ok if d)

class Auth(BaseModel): email: str; password: str
class BotIn(BaseModel): name: str; site_url: str = ""
class TextIn(BaseModel): title: str = "Pasted text"; text: str
class UrlIn(BaseModel): url: str; max_pages: int = 0; resume: bool = False
class Settings(BaseModel): email_mode: str
class ChatIn(BaseModel): message: str; session: str = "anon"; history: list = []
class EmailIn(BaseModel): sender: str; subject: str; body: str

@app.post("/api/signup")
def signup(a: Auth):
    if len(a.password) < 8: raise HTTPException(400, "Password must be 8+ characters")
    if db.one("select id from users where email=?", (a.email.lower(),)): raise HTTPException(400, "Email already registered")
    t = secrets.token_urlsafe(32); db.run("insert into users(email,pw,token) values(?,?,?)", (a.email.lower(), _hash(a.password), t))
    return {"token": t}
@app.post("/api/login")
def login(a: Auth):
    u = db.one("select * from users where email=?", (a.email.lower(),))
    if not u or not _check(a.password, u["pw"]): raise HTTPException(401, "Wrong email or password")
    return {"token": u["token"]}

def _new_bot(u, name, site_url):
    if MAX_BOTS and db.one("select count(*) n from bots where user_id=?", (u["id"],))["n"] >= MAX_BOTS: raise HTTPException(400, f"Plan limit reached: {MAX_BOTS} assistants")
    key = "pk_" + secrets.token_urlsafe(12)
    return db.run("insert into bots(user_id,name,site_url,public_key) values(?,?,?,?)", (u["id"], name, site_url, key)), key
def _url(x):
    x = x.strip()
    return x if x.startswith(("http://", "https://")) else "https://" + x

class QuickIn(BaseModel): url: str; name: str = ""

@app.post("/api/bots")
def create_bot(b: BotIn, u=Depends(current_user)):
    i, key = _new_bot(u, b.name, b.site_url); return {"id": i, "public_key": key}

@app.post("/api/bots/quick")
def quick_bot(q: QuickIn, u=Depends(current_user)):
    """One step: URL in -> bot created and the whole website learned."""
    url = _url(q.url)
    if not rag.safe_url(url): raise HTTPException(400, "Please enter a public website address, e.g. https://yourcompany.com")
    same = [x for x in db.rows("select id,public_key,site_url from bots where user_id=? order by id", (u["id"],)) if urlparse(_url(x["site_url"] or "")).netloc == urlparse(url).netloc]
    if same: i, key = same[0]["id"], same[0]["public_key"]; db.run("update bots set site_url=? where id=?", (url, i))  # reuse the assistant already made for this website
    else: i, key = _new_bot(u, q.name or urlparse(url).netloc, url)
    try: res = rag.crawl(i, url, budget=30)  # leave headroom under Vercel's 60 s limit
    except Exception as e:
        import traceback; traceback.print_exc()
        res = dict(pages=0, title="", warning="We couldn't finish reading this website (" + type(e).__name__ + "). Try again, use Deep read, or paste the key information as text.")
    deep = False
    if reader_client.configured() and (res["pages"] == 0 or "JavaScript" in res.get("warning", "")):  # plain crawl found little: hand over to the browser-based reader
        try: _start_reader({"id": i}, url); deep = True
        except Exception as e: print("reader start failed:", e)
    if res["title"] and not q.name and not deep: db.run("update bots set name=? where id=?", (res["title"][:60], i))  # with a deep read, the better title comes later
    return {"id": i, "public_key": key, "deep": deep, "reused": bool(same), **res}
@app.get("/api/bots")
def list_bots(u=Depends(current_user)):
    return db.rows("select id,name,site_url,public_key,email_mode,color,title,greeting,domain_lock,allowed_domains,(select count(*) from chunks where bot_id=bots.id and source<>'site-profile') as chunks, (select count(*) from chunks where bot_id=bots.id and emb is not null and source<>'site-profile') as indexed, auto_relearn, last_learned, learn_note, learn_mode from bots where user_id=?", (u["id"],))
@app.post("/api/bots/{bot_id}/settings")
def settings(s: Settings, b=Depends(own_bot)):
    if s.email_mode not in ("draft", "auto"): raise HTTPException(400, "email_mode must be draft or auto")
    db.run("update bots set email_mode=? where id=?", (s.email_mode, b["id"])); return {"ok": True}

@app.delete("/api/bots/{bot_id}")
def delete_bot(b=Depends(own_bot)):
    try: gmail.disconnect(b["id"])
    except Exception as e: print("gmail disconnect failed:", e)
    for t in ("chunks", "navlinks", "conversations", "leads", "emails", "guides", "gmail_accounts"): db.run(f"delete from {t} where bot_id=?", (b["id"],))
    db.run("delete from bots where id=?", (b["id"],)); return {"ok": True}

@app.post("/api/bots/{bot_id}/text")
def add_text(t: TextIn, b=Depends(own_bot)): return {"chunks": rag.add_document(b["id"], t.title, t.text)}
@app.post("/api/bots/{bot_id}/crawl")
def crawl(r: UrlIn, b=Depends(own_bot)):
    url = _url(r.url or b["site_url"])
    if not rag.safe_url(url): raise HTTPException(400, "URL must be a public http(s) address")
    try: return rag.crawl(b["id"], url, r.max_pages or None, budget=35, resume=r.resume)
    except Exception as e:
        import traceback; traceback.print_exc(); raise HTTPException(502, "We couldn't finish reading this website (" + type(e).__name__ + "). Try again or use Deep read.")

@app.post("/api/bots/{bot_id}/embed")
def embed_pending(b=Depends(own_bot)):
    """Indexes up to 100 not-yet-embedded chunks; the dashboard calls this until remaining == 0."""
    total = db.one("select count(*) n from chunks where bot_id=? and source<>?", (b["id"], "site-profile"))["n"]
    if not embed.available(): return {"enabled": False, "remaining": 0, "total": total}
    todo = db.rows("select id,text from chunks where bot_id=? and emb is null and source<>? order by id limit 100", (b["id"], "site-profile"))
    if todo:
        try:
            vecs = embed.docs([t["text"] for t in todo])
            db.run_many("update chunks set emb=? where id=?", [(v, t["id"]) for v, t in zip(vecs, todo)])
        except Exception as e:
            print("embed failed:", e); return {"enabled": True, "remaining": -1, "total": total}
    rem = db.one("select count(*) n from chunks where bot_id=? and emb is null and source<>?", (b["id"], "site-profile"))["n"]
    return {"enabled": True, "remaining": rem, "total": total}

@app.get("/api/bots/{bot_id}/sources")
def sources(b=Depends(own_bot)):
    return db.rows("select source, count(*) n from chunks where bot_id=? group by source order by n desc limit 100", (b["id"],))

class GuideIn(BaseModel): title: str; steps: str = ""; url: str = ""; target: str = ""

@app.get("/api/bots/{bot_id}/guide")
def guide_list(b=Depends(own_bot)): return db.rows("select id,title,steps,url,target from guides where bot_id=? order by id", (b["id"],))
@app.post("/api/bots/{bot_id}/guide")
def guide_add(g: GuideIn, b=Depends(own_bot)):
    if not g.title.strip(): raise HTTPException(400, "Please give this entry a name, e.g. 'Settings'")
    if db.one("select count(*) n from guides where bot_id=?", (b["id"],))["n"] >= 30: raise HTTPException(400, "Limit: 30 guide entries")
    url = g.url.strip()
    if url:
        url = urljoin(_url(b["site_url"]) if b["site_url"] else "", url)
        if urlparse(url).scheme not in ("http", "https"): raise HTTPException(400, "Page address must start with http(s):// or be a path like /account")
    i = db.run("insert into guides(bot_id,title,steps,url,target) values(?,?,?,?,?)", (b["id"], g.title.strip()[:80], g.steps.strip()[:600], url, g.target.strip()[:120]))
    return {"id": i}
@app.delete("/api/bots/{bot_id}/guide/{gid}")
def guide_del(gid: int, b=Depends(own_bot)):
    db.run("delete from guides where id=? and bot_id=?", (gid, b["id"])); return {"ok": True}
@app.get("/api/bots/{bot_id}/nav")
def nav_list(b=Depends(own_bot)): return db.rows("select label,url,area,note from navlinks where bot_id=? order by id limit 600", (b["id"],))

class FB(BaseModel): id: int; helpful: int
class LeadIn(BaseModel): name: str = ""; email: str; message: str = ""; question: str = ""
class Look(BaseModel): title: str = ""; color: str = ""; greeting: str = ""; domain_lock: bool = False; allowed_domains: str = ""

def _pub(key, request):
    b = db.one("select * from bots where public_key=?", (key,))
    if not b: raise HTTPException(404, "Unknown bot")
    if not _allowed(b, request): raise HTTPException(403, "This assistant isn't enabled for this website.")
    return b

@app.post("/api/chat/{public_key}/feedback")
def feedback(public_key: str, f: FB, request: Request):
    b = _pub(public_key, request)
    if f.helpful not in (1, -1): raise HTTPException(400, "helpful must be 1 or -1")
    db.run("update conversations set helpful=? where id=? and bot_id=?", (f.helpful, f.id, b["id"])); return {"ok": True}

@app.post("/api/chat/{public_key}/lead")
def lead(public_key: str, l: LeadIn, request: Request):
    """Human handoff: visitor leaves contact details when the bot couldn't answer."""
    b = _pub(public_key, request); ip = _ip(request); now = int(time.time())
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", l.email.strip()): raise HTTPException(400, "Please enter a valid email address")
    if db.one("select count(*) n from leads where ip=? and ts>?", (ip, now - 3600))["n"] >= 5: raise HTTPException(429, "Too many requests, please try later")
    db.run("insert into leads(bot_id,name,email,message,question,ip,ts) values(?,?,?,?,?,?,?)",
           (b["id"], l.name.strip()[:80], l.email.strip()[:120], l.message.strip()[:1000], l.question.strip()[:500], ip, now))
    if os.getenv("ALERT_WEBHOOK"):
        try: requests.post(os.getenv("ALERT_WEBHOOK"), json={"text": f"New lead for {b['name']}: {l.email} asked: {l.question[:200]}"}, timeout=5)
        except Exception: pass
    return {"ok": True}

@app.get("/api/widget/{key}")
def widget_cfg(key: str):
    b = db.one("select name,title,color,greeting from bots where public_key=?", (key,))
    if not b: raise HTTPException(404, "Unknown bot")
    return {"title": b["title"] or f"Chat with {b['name']}", "color": b["color"] or "", "greeting": b["greeting"] or ""}

@app.post("/api/bots/{bot_id}/appearance")
def appearance(a: Look, b=Depends(own_bot)):
    if a.color and not re.fullmatch(r"#[0-9a-fA-F]{6}", a.color): raise HTTPException(400, "Color must look like #4f46e5")
    doms = ",".join(sorted({_host(d.strip() if "//" in d else "//" + d.strip()) for d in a.allowed_domains.split(",") if d.strip()} - {""}))
    db.run("update bots set title=?,color=?,greeting=?,domain_lock=?,allowed_domains=? where id=?", (a.title.strip()[:60], a.color, a.greeting.strip()[:200], int(a.domain_lock), doms, b["id"]))
    return {"ok": True, "allowed_domains": doms}

@app.post("/api/bots/{bot_id}/verify")
def verify(b=Depends(own_bot)):
    """Checks whether the snippet is present on the customer's live website."""
    if not b["site_url"]: raise HTTPException(400, "Add your website address first")
    start = _url(b["site_url"]); urls = [start] + [n["url"] for n in db.rows("select url from navlinks where bot_id=? and area=? limit 3", (b["id"], "menu"))]
    for u in urls:
        r = rag._get(u)
        if r and b["public_key"] in r[1]: return {"installed": True, "url": r[0]}
    return {"installed": False, "url": start}

@app.get("/api/bots/{bot_id}/leads")
def leads(b=Depends(own_bot)): return db.rows("select name,email,question,message,created from leads where bot_id=? order by id desc limit 100", (b["id"],))

def _base(request):
    if os.getenv("APP_URL"): return os.getenv("APP_URL").rstrip("/")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    proto = request.headers.get("x-forwarded-proto") or ("http" if host.startswith(("localhost", "127.")) else "https")
    return f"{proto}://{host}"

@app.get("/api/bots/{bot_id}/gmail")
def gmail_status(b=Depends(own_bot)):
    a = db.one("select email,last_sync from gmail_accounts where bot_id=?", (b["id"],))
    return {"configured": gmail.configured(), "connected": bool(a), "email": a["email"] if a else "", "last_sync": a["last_sync"] if a else None}

@app.post("/api/bots/{bot_id}/gmail/auth-url")
def gmail_auth_url(request: Request, b=Depends(own_bot)):
    if not gmail.configured(): raise HTTPException(400, "Gmail isn't set up on this server yet (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing)")
    return {"url": gmail.auth_url(gmail.make_state(b["id"], b["user_id"]), _base(request) + "/api/gmail/callback")}

@app.get("/api/gmail/callback")
def gmail_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    st = gmail.read_state(state)
    if not st: raise HTTPException(400, "Invalid or expired connection request. Please try again from the dashboard.")
    if error or not code: return RedirectResponse("/?gmail=denied")
    bot = db.one("select id from bots where id=? and user_id=?", (st["b"], st["u"]))
    if not bot: raise HTTPException(404, "Bot not found")
    try:
        tok = gmail.exchange(code, _base(request) + "/api/gmail/callback"); email = gmail.profile(tok["access_token"])
    except Exception as e:
        print("gmail connect failed:", e); return RedirectResponse("/?gmail=error")
    if not tok.get("refresh_token"): return RedirectResponse("/?gmail=norefresh")
    gmail.save_account(bot["id"], email, tok["refresh_token"])
    return RedirectResponse(f"/?gmail=connected&bot={bot['id']}")

@app.post("/api/bots/{bot_id}/gmail/disconnect")
def gmail_disconnect(b=Depends(own_bot)): gmail.disconnect(b["id"]); return {"ok": True}

def _run_sync(b, **kw):
    try: return gmail.sync(b, **kw)
    except gmail.GmailAuthError as e: raise HTTPException(400, str(e))
    except Exception as e:
        print("gmail sync failed:", e); raise HTTPException(502, "Couldn't reach Gmail right now. Please try again.")

@app.post("/api/bots/{bot_id}/gmail/sync")
def gmail_sync(b=Depends(own_bot)): return _run_sync(b)

@app.post("/api/bots/{bot_id}/emails/{eid}/{action}")
def email_draft(eid: int, action: str, b=Depends(own_bot)):
    if action not in ("send", "discard"): raise HTTPException(404, "Unknown action")
    row = db.one("select * from emails where id=? and bot_id=? and status=?", (eid, b["id"], "draft_saved"))
    if not row: raise HTTPException(404, "No pending draft for this email")
    try: gmail.draft_action(b, row, action == "send")
    except gmail.GmailAuthError as e: raise HTTPException(400, str(e))
    except Exception as e: print("draft action failed:", e); raise HTTPException(502, "Gmail rejected that action (the draft may have been edited or sent already).")
    return {"ok": True}

def _cron_ok(request, secret):
    want = os.getenv("CRON_SECRET", ""); got = request.headers.get("authorization", "").removeprefix("Bearer ") or secret
    if not want or not hmac.compare_digest(got, want): raise HTTPException(401, "Unauthorized")

def _gmail_cron(budget=40):
    t0, out = time.time(), []
    for a in db.rows("select bot_id from gmail_accounts order by coalesce(last_sync,0) limit 5"):
        if time.time() - t0 > budget: break
        b = db.one("select * from bots where id=?", (a["bot_id"],))
        try: out.append({"bot": a["bot_id"], **gmail.sync(b, max_msgs=3, budget=12)})
        except Exception as e: print("cron sync failed:", e); out.append({"bot": a["bot_id"], "error": str(e)[:100]})
    return out

def _embed_some(bot_id, batches=2):
    if not embed.available(): return
    for _ in range(batches):
        todo = db.rows("select id,text from chunks where bot_id=? and emb is null and source<>? order by id limit 100", (bot_id, "site-profile"))
        if not todo: return
        try: vecs = embed.docs([t["text"] for t in todo]); db.run_many("update chunks set emb=? where id=?", [(v, t["id"]) for v, t in zip(vecs, todo)])
        except Exception as e: print("embed failed:", e); return

def _start_reader(b, url, request=None, background=False, max_pages=30):
    """background=True: the reader calls us back with the result when done (used by the scheduler); otherwise the dashboard polls."""
    cb = ""
    if background and request is not None:
        sig = hmac.new(os.getenv("READER_KEY", "").encode(), f"cb:{b['id']}".encode(), hashlib.sha256).hexdigest()
        cb = f"{_base(request)}/api/reader/callback?bot={b['id']}&sig={sig}"
    job = reader_client.start(url, max_pages, "auto", cb)
    db.run("update bots set reader_job=?, reader_job_ts=? where id=?", (job, int(time.time()), b["id"])); return job

def _ingest_reader_result(b, res):
    pages = [{**p, "emails": set(p.get("emails") or []), "phones": set(p.get("phones") or [])} for p in res["pages"]]
    site = _url(b["site_url"] or "x.invalid")
    out = rag.ingest_pages(b["id"], pages[0]["url"] if pages else site, pages, mode="deep", routes=res.get("routes"))
    if out["title"] and (not b["name"] or b["name"] == urlparse(site).netloc): db.run("update bots set name=? where id=?", (out["title"][:60], b["id"]))
    if res.get("warning") and not out.get("warning"): out["warning"] = res["warning"]
    return {**out, "rendered": res.get("rendered", 0)}

def _auto_relearn(request, budget=48):
    """Re-reads every website whose owner enabled automatic updates and whose last update is old enough."""
    t0, now, out = time.time(), int(time.time()), []
    for b in db.rows("select id from bots where reader_job is not null and coalesce(reader_job_ts,0) < ?", (now - 3600,)):  # lost/stale reader jobs
        db.run("update bots set reader_job=null where id=?", (b["id"],))
    due = db.rows("""select * from bots where reader_job is null and site_url is not null and site_url<>? and coalesce(last_attempt,0)<?
                     and ((auto_relearn=? and coalesce(last_learned,0)<?) or (auto_relearn=? and coalesce(last_learned,0)<?))
                     order by coalesce(last_learned,0) limit 3""", ("", now - 6 * 3600, "daily", now - 22 * 3600, "weekly", now - 6 * 86400 - 12 * 3600))
    for b in due:
        left = budget - (time.time() - t0)
        if left < 8: break
        url, r = _url(b["site_url"]), {"bot": b["id"]}
        db.run("update bots set last_attempt=? where id=?", (now, b["id"]))
        try:
            if not rag.safe_url(url): raise ValueError("website address is not public")
            if b.get("learn_mode") == "deep" and reader_client.configured():
                _start_reader(b, url, request, background=True); r["mode"] = "deep: reader started"
            else:
                res = rag.crawl(b["id"], url, 40, budget=min(20, left - 5))
                if res["pages"] == 0:
                    db.run("update bots set learn_note=? where id=?", ("The last automatic update couldn't read your website, so the previous knowledge was kept.", b["id"])); r["error"] = "unreadable"
                else:
                    r.update({k: res.get(k) for k in ("pages", "new", "changed", "unchanged", "removed")})
                    if "JavaScript" in res.get("warning", "") and reader_client.configured(): _start_reader(b, url, request, background=True); r["mode"] = "deep: reader started"
                    _embed_some(b["id"], 2)
        except Exception as e:
            print("auto relearn failed:", e); r["error"] = str(e)[:100]
        out.append(r)
    return out

@app.get("/api/cron/gmail")
def cron_gmail(request: Request, secret: str = ""):
    """Check connected inboxes (Vercel Cron or an external pinger)."""
    _cron_ok(request, secret); return {"synced": _gmail_cron()}

@app.get("/api/cron/relearn")
def cron_relearn(request: Request, secret: str = ""):
    """Refresh websites whose automatic update is due."""
    _cron_ok(request, secret); return {"relearned": _auto_relearn(request)}

@app.get("/api/cron/daily")
def cron_daily(request: Request, secret: str = ""):
    """The single daily Vercel Cron job: refresh websites, then check inboxes."""
    _cron_ok(request, secret); t0 = time.time(); r = _auto_relearn(request, budget=38)
    return {"relearned": r, "synced": _gmail_cron(max(5, 50 - (time.time() - t0)))}

class ArlIn(BaseModel): frequency: str
@app.post("/api/bots/{bot_id}/auto-relearn")
def set_auto_relearn(a: ArlIn, b=Depends(own_bot)):
    if a.frequency not in ("off", "daily", "weekly"): raise HTTPException(400, "frequency must be off, daily or weekly")
    db.run("update bots set auto_relearn=? where id=?", (a.frequency, b["id"])); return {"ok": True}

@app.get("/api/ai/status")
def ai_status(u=Depends(current_user)):
    """Lets the dashboard show whether the AI model and smart search are really working (and why not)."""
    return {"ai": llm.check(), "embeddings": embed.check()}

@app.get("/api/learn/config")
def learn_config(u=Depends(current_user)): return {"deep": reader_client.configured()}

@app.post("/api/bots/{bot_id}/learn/deep")
def learn_deep(r: UrlIn, b=Depends(own_bot)):
    """Starts a browser-based read of the website on the Reader service (for JavaScript-heavy sites)."""
    if not reader_client.configured(): raise HTTPException(400, "Deep reading isn't enabled on this server yet.")
    url = _url(r.url or b["site_url"])
    if not rag.safe_url(url): raise HTTPException(400, "URL must be a public http(s) address")
    try: job = _start_reader(b, url, max_pages=min(r.max_pages or 100, 150))
    except Exception as e:
        print("reader start failed:", e); raise HTTPException(502, "The reader service isn't responding (it may be waking up). Please try again in a minute.")
    db.run("update bots set site_url=coalesce(nullif(site_url,''),?) where id=?", (url, b["id"])); return {"job": job}

@app.get("/api/bots/{bot_id}/learn/status")
def learn_status(b=Depends(own_bot)):
    job = b.get("reader_job")
    if not job: return {"status": "idle"}
    try: s = reader_client.status(job)
    except Exception as e: print("reader poll failed:", e); return {"status": "running", "progress": {"phase": "waiting for the reader"}}
    if s["status"] == "error":
        db.run("update bots set reader_job=null where id=?", (b["id"],)); return {"status": "error", "error": s.get("error", "The reader could not read this website.")}
    if s["status"] != "done": return {"status": s["status"], "progress": s.get("progress", {})}
    db.run("update bots set reader_job=null where id=?", (b["id"],))
    return {"status": "done", **_ingest_reader_result(b, s["result"])}

@app.post("/api/reader/callback")
def reader_callback(payload: dict, bot: int = 0, sig: str = "", x_reader_key: str = Header("")):
    """The Reader posts finished background jobs here (signed per bot, so nobody else can feed a bot knowledge)."""
    key = os.getenv("READER_KEY", ""); want = hmac.new(key.encode(), f"cb:{bot}".encode(), hashlib.sha256).hexdigest()
    if not key or not hmac.compare_digest(x_reader_key, key) or not hmac.compare_digest(sig, want): raise HTTPException(401, "Unauthorized")
    b = db.one("select * from bots where id=?", (bot,))
    if not b or not b.get("reader_job") or b["reader_job"] != payload.get("job"): return {"ok": True, "ignored": True}
    db.run("update bots set reader_job=null where id=?", (bot,))
    if payload.get("status") == "done" and payload.get("result"):
        out = _ingest_reader_result(b, payload["result"]); _embed_some(bot, 1); return {"ok": True, "pages": out["pages"]}
    db.run("update bots set learn_note=? where id=?", ("The last automatic update failed: " + str(payload.get("error") or "the reader could not read the site")[:150], bot)); return {"ok": True}

@app.get("/demo/{key}")
def demo(key: str):
    b = db.one("select name from bots where public_key=?", (key,))
    if not b: raise HTTPException(404, "Unknown bot")
    n = html.escape(b["name"])
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{n}: chatbot preview</title>
<body style="font:16px system-ui;max-width:760px;margin:60px auto;padding:0 20px;color:#222"><h1>{n}</h1>
<p>This is a preview page. The chat bubble in the bottom-right corner is exactly how it will look on your website.</p>
<p style="color:#888">Click the bubble and ask a question about your business.</p>
<script src="/widget.js" data-key="{html.escape(key)}" data-title="Chat with {n}"></script></body>""")
@app.post("/api/bots/{bot_id}/upload")
async def upload(file: UploadFile = File(...), b=Depends(own_bot)):
    data = await file.read()
    if len(data) > 5_000_000: raise HTTPException(400, "File too large (5MB max)")
    if file.filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    else: text = data.decode("utf-8", "ignore")
    if len(text.strip()) < 20: raise HTTPException(400, "No readable text found in file")
    return {"chunks": rag.add_document(b["id"], file.filename, text)}
@app.delete("/api/bots/{bot_id}/knowledge")
def clear_knowledge(b=Depends(own_bot)):
    db.run("delete from chunks where bot_id=?", (b["id"],)); return {"ok": True}

@app.get("/api/health")
def health(): return {"ok": True, "db": "postgres" if db.PG else "sqlite", "ai_key_set": llm.available()}

@app.post("/api/chat/{public_key}")
def chat(public_key: str, c: ChatIn, request: Request):
    b = db.one("select * from bots where public_key=?", (public_key,))
    if not b: raise HTTPException(404, "Unknown bot")
    if not _allowed(b, request): raise HTTPException(403, "This assistant isn't enabled for this website.")
    ip = _ip(request); now = int(time.time())
    if db.one("select count(*) n from conversations where ip=? and ts>?", (ip, now - 60))["n"] >= 15: raise HTTPException(429, "Too many messages, slow down")
    if DAILY_LIMIT and db.one("select count(*) n from conversations where bot_id=? and ts>?", (b["id"], now - 86400))["n"] >= DAILY_LIMIT: raise HTTPException(429, "Daily chat limit reached")
    msg = c.message.strip()[:1000]
    if not msg: raise HTTPException(400, "Empty message")
    hist = [m for m in c.history if isinstance(m, dict) and "role" in m and "content" in m]
    ans, ok, srcs, acts = rag.answer(b, msg, hist)
    cid = db.run("insert into conversations(bot_id,session,ip,ts,question,answer,answered) values(?,?,?,?,?,?,?)", (b["id"], c.session[:64], ip, now, msg, ans, int(ok)))
    return {"id": cid, "answer": ans, "answered": ok, "handoff": not ok, "sources": srcs, "actions": acts}

@app.get("/api/bots/{bot_id}/insights")
def get_insights(b=Depends(own_bot)):
    t = insights.topics(b["id"]); st = db.one("select count(*) n, coalesce(sum(1-answered),0) u from conversations where bot_id=?", (b["id"],))
    gaps = db.rows("select min(question) question, count(*) n from conversations where bot_id=? and answered=0 group by lower(question) order by n desc limit 15", (b["id"],))
    fb = db.one("select coalesce(sum(case when helpful=1 then 1 else 0 end),0) up, coalesce(sum(case when helpful=-1 then 1 else 0 end),0) down from conversations where bot_id=?", (b["id"],))
    bad = db.rows("select question, answer from conversations where bot_id=? and helpful=-1 order by id desc limit 10", (b["id"],))
    return {"total": int(st["n"]), "unanswered": int(st["u"]), "topics": t[:12], "gaps": gaps, "summary": insights.summary(b["id"]),
            "feedback": {"up": int(fb["up"]), "down": int(fb["down"])}, "bad": bad}
@app.get("/api/bots/{bot_id}/conversations")
def convs(b=Depends(own_bot)): return db.rows("select question,answer,answered,helpful,created from conversations where bot_id=? order by id desc limit 100", (b["id"],))
@app.post("/api/bots/{bot_id}/emails/process")
def process_email(e: EmailIn, b=Depends(own_bot)): return email_assistant.handle(b, e.sender, e.subject, e.body)
@app.get("/api/bots/{bot_id}/emails")
def list_emails(b=Depends(own_bot)): return db.rows("select id,sender,subject,category,reason,reply,status,created from emails where bot_id=? order by id desc limit 100", (b["id"],))

@app.get("/widget.js")
def widget(): return FileResponse(os.path.join(HERE, "static/widget.js"), media_type="application/javascript")
@app.get("/")
def home(): return FileResponse(os.path.join(HERE, "static/dashboard.html"))
