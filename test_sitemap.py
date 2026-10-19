import os, re, threading
os.environ.update(DB_PATH="/tmp/s.db")
if os.path.exists("/tmp/s.db"): os.remove("/tmp/s.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
LOREM = " ".join(["We bake fresh bread and cakes every morning using local ingredients and family recipes."] * 6)
HOME = f"""<html><head><title>Ravi Bakery</title></head><body>
<header><button aria-label="Search">x</button><button>Dark mode</button></header>
<div class="topbar"><a href="/pricing">Pricing</a><a href="/orders/track">Track my order</a><a href="/blog/post1">Read more</a><a href="/cart" aria-label="Cart"><svg></svg></a></div>
<main><p>Welcome. {LOREM}</p><div role="tab">Reviews</div><form><button type="submit">Submit</button></form></main>
<script src="/static/app.js"></script></body></html>"""
APP_JS = 'const routes=[{path:"/settings",label:"Account settings"},{path:"/billing"},{path:"/dashboard"}]; fetch("/api/v1/users"); var l="/static/logo.png"; var x="/invoices"; var z="/zzz-random";'
page = lambda t, b: f"<html><head><title>{t}</title></head><body><main><p>{b} {LOREM}</p></main></body></html>"
SITE = {"/": HOME, "/pricing": page("Pricing", "Cakes cost 500 rupees."), "/orders/track": page("Track my order", "Enter your order number to see where your cake is."), "/cart": page("Cart", "Your cart."), "/static/app.js": APP_JS}
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        b = SITE.get(urlparse(s.path).path)
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "application/javascript" if s.path.endswith(".js") else "text/html"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1", 8775), H).serve_forever, daemon=True).start()
import rag, llm, db
rag.safe_url = lambda u: True; llm.ask = lambda *a, **k: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app); ok = lambda x: "✅" if x else "❌"
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H_ = {"Authorization": "Bearer " + t}
r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8775"}, headers=H_).json(); bid = r["id"]; key = r["public_key"]
nav = c.get(f"/api/bots/{bid}/nav", headers=H_).json(); by = lambda a: {x["label"]: x for x in nav if x["area"] == a}
cnt = {a: len(by(a)) for a in ("menu", "page", "link", "tool", "route")}; print("site map found:", cnt)
print("menu built from plain <div>s:", ok("Track my order" in {x["label"] for x in nav}), "| icon-only link (aria-label):", ok("Cart" in {x["label"] for x in nav}))
print("tools:", {k: v["note"] for k, v in by("tool").items()}, "| submit/generic excluded:", ok("Submit" not in by("tool") and "Read more" not in {x["label"] for x in nav}))
print("app pages from JS code:", {k: v["url"].replace("http://127.0.0.1:8775", "") for k, v in by("route").items()}, "| junk excluded:", ok(not any(p in " ".join(x["url"] for x in nav) for p in ("/api/", "logo.png", "zzz"))))
ask = lambda q: c.post(f"/api/chat/{key}", json={"message": q}).json()
for q in ("where is the billing page", "where can I change my account settings", "where is the search", "how do I track my order", "where can I find invoices"):
    a = ask(q); x = (a["actions"] or [{}])[0]; print(f"  {q!r} ->", x.get("label"), x.get("url", "").replace("http://127.0.0.1:8775", ""), "| target:", x.get("target"))
rag.crawl(bid, "http://127.0.0.1:8775"); nav2 = c.get(f"/api/bots/{bid}/nav", headers=H_).json(); print("re-learn keeps map without duplicates:", ok(len(nav2) == len(nav) and len({(x["label"], x["url"]) for x in nav2}) == len(nav2)))
# relevance ranking on a big site: the right page must reach the AI even among hundreds of links
db.run_many("insert into navlinks(bot_id,label,url,area,note) values(?,?,?,?,?)", [(bid, f"Page {i}", f"http://127.0.0.1:8775/p{i}", "link", "") for i in range(400)] + [(bid, "Warranty claims", "http://127.0.0.1:8775/warranty", "link", "")])
d = rag.destinations(bid, [], "where do I file a warranty claim"); print("big site: relevant link offered:", ok("Warranty claims" in [x["label"] for x in d]), "| list capped:", len(d) <= 70)
seen = {}
def fake(system, user, *a, **k):
    seen["sys"], seen["user"] = system, user; n = re.search(r"D(\d+): Billing", user); return "Open Billing from the account area. [[GO:%s]] [[GO:999]]" % n.group(1)
llm.ask = fake; a = ask("where is billing"); print("AI path:", a["actions"][:1], "| told about login:", ok("may need login" in seen["user"] and "log in first" in seen["sys"]), "| invented id ignored:", ok(len(a["actions"]) == 1))
