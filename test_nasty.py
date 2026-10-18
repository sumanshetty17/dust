"""Messy real-world website: malformed links, NUL bytes, bad sitemap, 3000-level nesting, long tracking query string."""
import os, threading
os.environ.setdefault("DB_PATH", "/tmp/n.db")
if "DATABASE_URL" not in os.environ and os.path.exists("/tmp/n.db"): os.remove("/tmp/n.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
LOREM = " ".join(["We bake fresh bread and cakes every morning using local ingredients and family recipes."] * 6)
DEEP = "<div>" * 3000 + "<a href='/deep'>Deep link</a>" + "</div>" * 3000
HOME = f"""<html><head><title>Nasty site \x00 with NUL</title></head><body>
<header><nav><a href="https://[object Object]">Broken 1</a><a href="http://[::1">Broken 2</a><a href="http://exa mple.com/x">Space host</a><a href="/about">About</a><a href="http://example.com:99999999/p">Bad port</a></nav></header>
<main><p>Welcome\x00World. {LOREM}</p><button aria-label="Search\x00"></button>{DEEP}</main>
<script src="http://[bad"></script><script src="/app.js"></script></body></html>"""
SITE = {"/": HOME, "/about": f"<html><head><title>About</title></head><body><p>About us. {LOREM}</p><a href='/ok'>OK</a></body></html>", "/ok": f"<html><body><p>OK page {LOREM}</p></body></html>",
        "/deep": f"<html><body><p>Deep page {LOREM}</p></body></html>", "/app.js": 'var r=[{path:"/settings",label:"Settings\x00"}];',
        "/sitemap.xml": "<urlset><url><loc>http://[broken</loc></url><url><loc>http://127.0.0.1:8776/ok</loc></url></urlset>"}
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        b = SITE.get(urlparse(s.path).path)
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "text/html; charset=utf-8"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1", 8776), H).serve_forever, daemon=True).start()
import rag, llm
_real_safe = rag.safe_url; rag.safe_url = lambda u: True; llm.ask = lambda *a, **k: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app, raise_server_exceptions=False); ok = lambda x: "✅" if x else "❌"
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H_ = {"Authorization": "Bearer " + t}
r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8776/?ad_id=729031234271&adg_id=171273071999&campaign_id=2202603617"}, headers=H_)
print("quick create status:", r.status_code, "| body:", r.text[:150])
if r.status_code == 200:
    j = r.json(); key = j["public_key"]; print("pages read:", j["pages"], "| title:", repr(j["title"]), "| warning:", j["warning"][:50])
    nav = c.get(f"/api/bots/{j['id']}/nav", headers=H_).json(); print("site map items:", len(nav), "| broken links stored:", ok(not any("[" in x["url"] or " " in x["url"] for x in nav)), "| app page found:", [x["label"] for x in nav if x["area"] == "route"])
    a = c.post(f"/api/chat/{key}", json={"message": "tell me about the deep page"}).json(); print("chat works:", ok("answered" in a))
rag.safe_url = _real_safe
bad = c.post("/api/bots/quick", json={"url": "http://[bad"}, headers=H_); print("malformed address typed by the user -> status:", bad.status_code, "| friendly JSON message:", ok(bad.headers["content-type"].startswith("application/json")), bad.text[:90])
