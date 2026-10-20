import os as _o; _o.environ["WEB_RESEARCH"] = "0"
import os, re, time, threading
os.environ.update(DB_PATH="/tmp/sc.db", MAX_PAGES="60")
if "DATABASE_URL" not in os.environ and os.path.exists("/tmp/sc.db"): os.remove("/tmp/sc.db")
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
LOREM = " ".join(["We bake fresh bread and cakes every morning using local ingredients and family recipes."] * 4)
pg = lambda t, body, extra="": f"<html><head><title>{t}</title></head><body><header><nav><a href='/'>Home</a><a href='/pricing'>Pricing</a></nav></header><main>{body}</main><footer><a href='/privacy'>Privacy policy</a></footer>{extra}</body></html>"
SITE = {"/": pg("Ravi Bakery", f"<p>Welcome. {LOREM}</p>" + "".join(f"<a href='/list{i}'>Catalogue {i}</a>" for i in range(1, 6))),
        "/pricing": pg("Pricing", f"<p>Cakes cost 500 rupees. {LOREM}</p>"), "/privacy": pg("Privacy policy", f"<p>We respect your privacy. {LOREM}</p>")}
for i in range(1, 6): SITE[f"/list{i}"] = pg(f"Catalogue {i}", "".join(f"<a href='/p{n}'>Product {n}</a>" for n in range((i - 1) * 30 + 1, i * 30 + 1)))
for n in range(1, 151): SITE[f"/p{n}"] = pg(f"Product {n}", f"<p>Product {n} special feature: zorbonium{n}.</p>")
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        b = SITE.get(urlparse(s.path).path)
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "text/html"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8779), H).serve_forever, daemon=True).start()
import rag, llm, db
rag.safe_url = lambda u: True; llm.ask = lambda *a, **k: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app); ok = lambda x: "✅" if x else "❌"
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H_ = {"Authorization": "Bearer " + t}
t0 = time.time(); r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8779"}, headers=H_).json(); bid, key = r["id"], r["public_key"]
print(f"1st pass: {r['pages']} pages (cap 60), more waiting: {r['more']} | {time.time()-t0:.1f}s")
passes = 1
while r["more"] > 0 and passes < 12:
    r = c.post(f"/api/bots/{bid}/crawl", json={"url": "http://127.0.0.1:8779", "resume": True}, headers=H_).json(); passes += 1
total = db.one("select count(distinct source) n from chunks where bot_id=? and substr(source,1,4)=?", (bid, "http"))["n"]
print(f"finished after {passes} passes: {total} pages learned (site has 158) | {time.time()-t0:.1f}s total |", ok(total >= 158), "| nothing left queued:", ok(db.one("select crawl_state from bots where id=?", (bid,))["crawl_state"] is None))
nav = c.get(f"/api/bots/{bid}/nav", headers=H_).json(); print("site map items:", len(nav), "| menu kept across passes:", ok({"Home", "Pricing", "Privacy policy"} <= {x["label"] for x in nav}))
ask = lambda q: c.post(f"/api/chat/{key}", json={"message": q}).json()
a = ask("what is the special feature of product 137"); print("question about page #137 (read in a later pass):", ok("zorbonium137" in a["answer"]))
t1 = time.time(); ask("what is the special feature of product 12"); ask("what is the special feature of product 99"); print(f"2 more questions on a 158-page site: {time.time()-t1:.2f}s")
i1 = rag._index(bid); i2 = rag._index(bid); print("index reused until knowledge changes:", ok(i1 is i2)); db.run("insert into chunks(bot_id,source,text) values(?,?,?)", (bid, "extra", "x")); print("rebuilt after a change:", ok(rag._index(bid) is not i1))
print("== directions ==")
for q in ("where is the privacy policy", "where can I find pricing"):
    a = ask(q); x = (a["actions"] or [{}])[0]; print(f"  {q!r} -> {a['answer'][:110]} | button: {x.get('url','').replace('http://127.0.0.1:8779','')}")
seen = {}
def fake(system, user, *a, **k): seen["u"] = user; n = re.search(r"D(\d+): Privacy policy", user); return "Scroll to the footer and click it. [[GO:%s]]" % n.group(1)
llm.ask = fake; a = ask("where is your privacy policy"); print("AI is told where the link is:", ok("link in the footer at the bottom of the page" in seen["u"]), "| button:", ok(a["actions"] and a["actions"][0]["url"].endswith("/privacy"))); llm.ask = lambda *a, **k: None
print("== no limits / reuse / delete ==")
r2 = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8779/"}, headers=H_).json(); print("same website again -> same assistant:", ok(r2["id"] == bid and r2["reused"]), "| bots:", len(c.get("/api/bots", headers=H_).json()))
codes = [c.post("/api/bots", json={"name": f"Bot {i}"}, headers=H_).status_code for i in range(8)]; print("created 8 more assistants:", codes.count(200), "of 8 ok (old limit was 3)")
t2 = c.post("/api/signup", json={"email": "x@evil.test", "password": "password1"}).json()["token"]
print("another user can't delete it:", c.delete(f"/api/bots/{bid}", headers={"Authorization": "Bearer " + t2}).status_code, "| owner deletes:", c.delete(f"/api/bots/{bid}", headers=H_).status_code, "| data gone:", ok(db.one("select count(*) n from chunks where bot_id=?", (bid,))["n"] == 0 and db.one("select count(*) n from navlinks where bot_id=?", (bid,))["n"] == 0))
