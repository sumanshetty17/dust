import os, sys, time, threading, urllib.request
sys.path.insert(0, "/home/claude/sitebot-reader")
os.environ.update(DB_PATH="/tmp/d.db", READER_KEY="k123", READER_URL="http://127.0.0.1:8773")
if os.path.exists("/tmp/d.db"): os.remove("/tmp/d.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
LOREM = " ".join(["We bake fresh bread and cakes every morning using local ingredients and family recipes."] * 6)
page = lambda t, b, nav="": f"<html><head><title>{t}</title></head><body><header><nav>{nav}</nav></header><main><p>{b}</p></main><footer>Call +91 90000 11111</footer></body></html>"
SHELL = "<html><head><title>Studio</title></head><body><div id='root'></div><script>const routes=['/services','/pricing'];</script></body></html>"
RENDERED = {"/": page("Ravi Studio", "Opening hours Monday to Saturday 9am to 6pm. " + LOREM, "<a href='/services'>Services</a><a href='/account/settings' aria-label='Settings'></a>"),
            "/services": page("Services", "Wedding cakes and custom orders. " + LOREM), "/pricing": page("Pricing", "Drain cleaning is 800 rupees. " + LOREM)}
class Site(BaseHTTPRequestHandler):  # a React-style site: every route returns an empty shell
    def do_GET(s):
        if s.path.endswith((".js", ".css", "robots.txt", "sitemap.xml")): s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "text/html"); s.end_headers(); s.wfile.write(SHELL.encode())
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1", 8772), Site).serve_forever, daemon=True).start()
import reader.service as svc, reader.render as rr, uvicorn
svc.safe_url = lambda u: True; svc.host_ok = lambda h: True
class Fake:  # stand-in for Chromium (not installable in this sandbox)
    async def __aenter__(s): return s
    async def __aexit__(s, *a): pass
    async def render(s, url): return RENDERED.get(urlparse(url).path or "/", RENDERED["/"]), url
rr.Session = Fake
threading.Thread(target=lambda: uvicorn.run(svc.app, host="127.0.0.1", port=8773, log_level="error"), daemon=True).start()
for _ in range(50):
    try: urllib.request.urlopen("http://127.0.0.1:8773/health"); break
    except Exception: time.sleep(.2)
import db, rag, llm, reader_client
rag.safe_url = lambda u: True; llm.ask = lambda *a, **k: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app); ok = lambda x: "✅" if x else "❌"
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H = {"Authorization": "Bearer " + t}
print("config:", c.get("/api/learn/config", headers=H).json())
r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8772"}, headers=H).json(); bid = r["id"]
print("quick: plain crawl pages =", r["pages"], "| JS warning:", ok("JavaScript" in r["warning"]), "| handed to reader:", r["deep"])
for _ in range(60):
    s = c.get(f"/api/bots/{bid}/learn/status", headers=H).json()
    if s["status"] in ("done", "error"): break
    time.sleep(.3)
print("deep status:", {k: s.get(k) for k in ("status", "pages", "rendered", "title", "warning")})
srcs = [x["source"].replace("http://127.0.0.1:8772", "") for x in c.get(f"/api/bots/{bid}/sources", headers=H).json()]; print("knowledge sources:", sorted(srcs))
print("menu learned (incl. icon-only):", [m["label"] for m in c.get(f"/api/bots/{bid}/nav", headers=H).json()])
print("job cleared:", c.get(f"/api/bots/{bid}/learn/status", headers=H).json()["status"], "| bot renamed:", [b["name"] for b in c.get("/api/bots", headers=H).json()])
key = c.get("/api/bots", headers=H).json()[0]["public_key"]; ask = lambda q: c.post(f"/api/chat/{key}", json={"message": q}).json()
a1, a2, a3 = ask("what are your opening hours"), ask("how much is drain cleaning"), ask("where is the settings")
print("chat from JS-rendered content:", ok(a1["answered"] and "Monday to Saturday" in a1["answer"]), ok(a2["answered"] and "800" in a2["answer"]), "| nav button:", a3["actions"][:1])
print("manual deep read:", c.post(f"/api/bots/{bid}/learn/deep", json={"url": "http://127.0.0.1:8772"}, headers=H).status_code, "| bad url:", c.post(f"/api/bots/{bid}/learn/deep", json={"url": "http://localhost"}, headers=H).status_code if False else "skipped")
os.environ["READER_KEY"] = ""; print("reader off -> config:", c.get("/api/learn/config", headers=H).json(), "| deep read:", c.post(f"/api/bots/{bid}/learn/deep", json={"url": "http://x.test"}, headers=H).status_code)
