import os as _o; _o.environ["WEB_RESEARCH"] = "0"
import os, sys, time, hmac, hashlib, threading, urllib.request, requests
sys.path.insert(0, "/home/claude/sitebot-reader")
os.environ.update(DB_PATH="/tmp/r.db", READER_KEY="k123", READER_URL="http://127.0.0.1:8773", CRON_SECRET="cron123", GEMINI_API_KEY="fake")
if os.path.exists("/tmp/r.db"): os.remove("/tmp/r.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
LOREM = " ".join(["We bake fresh bread and cakes every morning using local ingredients and family recipes."] * 6)
def nav(): return "".join(f"<a href='{p}'>{p.strip('/') or 'Home'}</a>" for p in PAGES if p != "/robots.txt")
page = lambda t, b: f"<html><head><title>{t}</title></head><body><header><nav>{nav()}</nav></header><main><p>{b}</p></main></body></html>"
BODY = {"/": ("Ravi Bakery", "Welcome. " + LOREM), "/about": ("About", "Our story. " + LOREM), "/pricing": ("Pricing", "Drain cleaning costs 800 rupees. " + LOREM)}
PAGES = {k: None for k in BODY}; FAIL = {"on": False}
def render_site(p): return page(*BODY[p]) if p in BODY else None
SHELL = "<html><head><title>Studio</title></head><body><div id='root'></div><script>const routes=['/pricing'];</script></body></html>"
RENDERED = {"/": page("Ravi Studio", "Studio welcome. " + LOREM), "/pricing": page("Pricing", "Wedding cake costs 1000 rupees. " + LOREM)}
def serve(port, fn):
    class H(BaseHTTPRequestHandler):
        def do_GET(s):
            b = None if FAIL["on"] and port == 8771 else fn(urlparse(s.path).path)
            if b is None: s.send_response(500 if FAIL["on"] and port == 8771 else 404); s.end_headers(); return
            s.send_response(200); s.send_header("Content-Type", "text/html"); s.end_headers(); s.wfile.write(b.encode())
        def log_message(*a): pass
    threading.Thread(target=HTTPServer(("127.0.0.1", port), H).serve_forever, daemon=True).start()
serve(8771, render_site); serve(8772, lambda p: None if p.endswith((".js", ".css", ".xml", ".txt")) else SHELL)
import numpy as np, reader.service as svc, reader.render as rr, uvicorn, embed, rag, llm, db
svc.safe_url = lambda u: True; svc.host_ok = lambda h: True; rag.safe_url = lambda u: True; llm.ask = lambda *a, **k: None
class Fake:
    async def __aenter__(s): return s
    async def __aexit__(s, *a): pass
    async def render(s, url): return RENDERED.get(urlparse(url).path or "/", RENDERED["/"]), url
rr.Session = Fake
EMB = []
def hv(t):
    v = np.zeros(384, dtype=np.float32)
    for w in rag.tokens(t): v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 384] += 1
    return v / (np.linalg.norm(v) or 1)
embed.docs = lambda ts: (EMB.append(len(ts)), [embed.enc(hv(t)) for t in ts])[1]; embed.query = lambda t: hv(t)
import main
threading.Thread(target=lambda: uvicorn.run(svc.app, host="127.0.0.1", port=8773, log_level="error"), daemon=True).start()
threading.Thread(target=lambda: uvicorn.run(main.app, host="127.0.0.1", port=8774, log_level="error"), daemon=True).start()
for port in (8773, 8774):
    for _ in range(60):
        try: urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health" if port == 8774 else "http://127.0.0.1:8773/health"); break
        except Exception: time.sleep(.2)
S = "http://127.0.0.1:8774"; cron = {"Authorization": "Bearer cron123"}; ok = lambda x: "✅" if x else "❌"
rq = lambda m, p, **k: requests.request(m, S + p, **k)
t = rq("POST", "/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H = {"Authorization": "Bearer " + t}
def embed_all(bid):
    while rq("POST", f"/api/bots/{bid}/embed", headers=H).json()["remaining"] > 0: pass
def old(bid, days=8): db.run("update bots set last_learned=?, last_attempt=null where id=?", (int(time.time()) - days * 86400, bid))
def ask(key, q): return rq("POST", f"/api/chat/{key}", json={"message": q}).json()
bot = lambda bid: db.one("select * from bots where id=?", (bid,))
print("== plain website, content changes ==")
r = rq("POST", "/api/bots/quick", json={"url": "http://127.0.0.1:8771"}, headers=H).json(); bid = r["id"]; key = r["public_key"]; embed_all(bid)
first = sum(EMB); print("first learn:", {k: r[k] for k in ("pages", "new", "changed", "unchanged")}, "| chunks embedded:", first, "| auto_relearn default:", bot(bid)["auto_relearn"])
before = {x["source"]: x["id"] for x in db.rows("select source,min(id) id from chunks where bot_id=? group by source", (bid,))}
BODY["/pricing"] = ("Pricing", "Drain cleaning costs 900 rupees. " + LOREM); BODY["/contact"] = ("Contact", "Visit us at 12 MG Road. " + LOREM); del BODY["/about"]; del PAGES["/about"]; PAGES["/contact"] = None
print("not due yet:", rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"])
old(bid); res = rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"]; print("cron:", res)
after = {x["source"]: x["id"] for x in db.rows("select source,min(id) id from chunks where bot_id=? group by source", (bid,))}
u = "http://127.0.0.1:8771"; a = ask(key, "how much is drain cleaning")["answer"]
print("only new+changed pages embedded again:", ok(sum(EMB) - first == 2), "| unchanged page kept its data:", ok(after[u + "/"] == before[u + "/"]), "| changed page rewritten:", ok(after[u + "/pricing"] != before[u + "/pricing"]))
print("answer reflects new price:", ok("900" in a and "800" not in a), "| removed page kept for now (no data loss from one crawl):", ok(u + "/about" in after), "| note:", bot(bid)["learn_note"])
db.run("update chunks set seen=? where bot_id=? and source=?", (int(time.time()) - 30 * 86400, bid, u + "/about")); old(bid); res = rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"]
print("page gone 3+ weeks is forgotten:", ok(res[0]["removed"] == 1 and not db.one("select 1 x from chunks where bot_id=? and source=?", (bid, u + "/about"))))
print("== owner settings / failures ==")
print("setting:", rq("POST", f"/api/bots/{bid}/auto-relearn", json={"frequency": "hourly"}, headers=H).status_code, rq("POST", f"/api/bots/{bid}/auto-relearn", json={"frequency": "off"}, headers=H).status_code)
old(bid); print("off -> skipped:", rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"])
rq("POST", f"/api/bots/{bid}/auto-relearn", json={"frequency": "daily"}, headers=H); old(bid, 2); n = db.one("select count(*) n from chunks where bot_id=?", (bid,))["n"]; ll = bot(bid)["last_learned"]; FAIL["on"] = True
res = rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"]; FAIL["on"] = False
print("site down:", res, "| knowledge kept:", ok(db.one("select count(*) n from chunks where bot_id=?", (bid,))["n"] == n), "| retry still due:", ok(bot(bid)["last_learned"] == ll), "|", bot(bid)["learn_note"][:60])
print("bots list has fields:", {k: v for k, v in rq("GET", "/api/bots", headers=H).json()[0].items() if k in ("auto_relearn", "learn_mode")})
print("cron auth:", rq("GET", "/api/cron/relearn").status_code, rq("GET", "/api/cron/relearn?secret=bad").status_code, rq("GET", "/api/cron/daily?secret=cron123").json().keys())
print("== JavaScript website: background re-learn through the reader callback ==")
r = rq("POST", "/api/bots/quick", json={"url": "http://127.0.0.1:8772"}, headers=H).json(); b2 = r["id"]; k2 = r["public_key"]; print("quick -> deep:", r["deep"])
for _ in range(80):
    s = rq("GET", f"/api/bots/{b2}/learn/status", headers=H).json()
    if s["status"] in ("done", "error"): break
    time.sleep(.25)
embed_all(b2); print("deep done:", s["status"], "| learn_mode:", bot(b2)["learn_mode"], "| answer:", "1000" in ask(k2, "how much is a wedding cake")["answer"])
RENDERED["/pricing"] = page("Pricing", "Wedding cake costs 1100 rupees. " + LOREM); old(b2); stamp = bot(b2)["last_learned"]
res = rq("GET", "/api/cron/relearn", headers=cron).json()["relearned"]; print("cron:", res)
for _ in range(80):
    if bot(b2)["reader_job"] is None and bot(b2)["last_learned"] > stamp: break
    time.sleep(.25)
print("finished by itself (nobody polled):", ok(bot(b2)["reader_job"] is None and bot(b2)["last_learned"] > stamp), "| new price live:", ok("1100" in ask(k2, "how much is a wedding cake")["answer"]), "|", bot(b2)["learn_note"][:70])
print("== callback security ==")
sig = lambda i: hmac.new(b"k123", f"cb:{i}".encode(), hashlib.sha256).hexdigest(); cb = lambda i, s, k, body: requests.post(f"{S}/api/reader/callback?bot={i}&sig={s}", json=body, headers={"X-Reader-Key": k}).status_code
db.run("update bots set reader_job=? where id=?", ("job-x", b2)); body = {"job": "job-x", "status": "done", "result": {"pages": [{"url": "http://evil.test/", "title": "FAKE", "desc": "", "ld": [], "menu": [], "lines": ["hacked"], "emails": [], "phones": []}]}}
print("wrong key:", cb(b2, sig(b2), "nope", body), "| wrong signature:", cb(b2, "0" * 64, "k123", body), "| signature of another bot:", cb(b2, sig(bid), "k123", body), "| nothing was ingested:", ok(not db.one("select 1 x from chunks where bot_id=? and source=?", (b2, "http://evil.test/"))))
print("unknown job ignored:", requests.post(f"{S}/api/reader/callback?bot={b2}&sig={sig(b2)}", json={**body, "job": "other"}, headers={"X-Reader-Key": "k123"}).json())
db.run("update bots set reader_job=?, reader_job_ts=? where id=?", ("ghost", int(time.time()) - 7200, b2)); old(b2); rq("GET", "/api/cron/relearn", headers=cron); print("stale reader job cleared by scheduler:", ok(bot(b2)["reader_job"] != "ghost"))
