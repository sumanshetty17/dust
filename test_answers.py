import os, re, threading, time
os.environ.update(DB_PATH="/tmp/an.db"); os.environ.pop("ANTHROPIC_API_KEY", None); os.environ["GEMINI_API_KEY"] = "fake"
if "DATABASE_URL" not in os.environ and os.path.exists("/tmp/an.db"): os.remove("/tmp/an.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
VENUES = ["Ikshaa Convention", "Royal Orchid Gardens", "Lotus Grand Banquet", "Sapphire Farmhouse", "Green Meadows Resort", "Palace Grounds Hall", "Emerald Lakeview", "Golden Petal Banquets", "Silver Oak Convention", "Maple Leaf Gardens", "Sunrise Marriage Hall", "Heritage Courtyard"]
nav = "<header><nav><a href='/'>Home</a><a href='/wedding-venues-in-bangalore'>Venues</a><a href='/wedding-invitation-cards'>Invitations</a></nav></header>"
pg = lambda t, b: f"<html><head><title>{t}</title></head><body>{nav}<main>{b}</main></body></html>"
INVITE = "Every e-wedding card maker platform gives you different template options for the names of the couple. Choose the names style you like. Add the names, the date and the venue. " * 6
SITE = {"/": pg("The Wedding Company - Book Venues, End to End Wedding Services", "We help you book wedding venues, decorators, photographers and invitation cards across Bangalore."),
        "/wedding-invitation-cards": pg("Wedding Invitation Card - Download Your Digital e Wedding Card Online", f"<p>{INVITE}</p>"),
        "/wedding-venues-in-bangalore": pg("Wedding Venues in Bangalore", "".join(f"<h3>{v}</h3><p>Behind Brigade Meadow 114, Pipeline Road, Kaggalipura, Bengaluru, Karnataka 560082. Price 600 - 800 rupees per plate. Parking for 14 cars. Open mantap with glass house and lawn.</p>" for v in VENUES))}
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        b = SITE.get(urlparse(s.path).path)
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "text/html"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1", 8780), H).serve_forever, daemon=True).start()
import rag, llm, embed, db, requests
rag.safe_url = lambda u: True; embed.query = lambda t: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app); ok = lambda x: "✅" if x else "❌"; real_ask = llm.ask; llm.ask = lambda *a, **k: None
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H_ = {"Authorization": "Bearer " + t}
r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8780"}, headers=H_).json(); bid, key = r["id"], r["public_key"]; bot = db.one("select * from bots where id=?", (bid,))
print("== 1. your screenshot: AI unavailable, follow-up question ==")
hist = [{"role": "user", "content": "which wedding venues do you have in Bangalore"}, {"role": "assistant", "content": "We have many venues in Bangalore."}]
a = c.post(f"/api/chat/{key}", json={"message": "just give me the venue names", "history": hist}).json()
print("  with chat history ->", repr(a["answer"][:105]), "| venue page link:", ok(a["actions"] and a["actions"][0]["url"].endswith("/wedding-venues-in-bangalore")), "| venue names shown:", ok("Ikshaa Convention" in a["answer"] or "Royal Orchid" in a["answer"]), "| not the invitation page:", ok("Invitation" not in a["answer"][:60]))
a = c.post(f"/api/chat/{key}", json={"message": "just give me the venue names"}).json()
print("  without history   ->", ok(a["actions"] and a["actions"][0]["url"].endswith("/wedding-venues-in-bangalore")), "(page address words now count as keywords)")
print("== 2. AI call: model fallback chain ==")
class Resp:
    def __init__(s, code, body): s.status_code, s._b = code, body
    def json(s): return s._b
    def raise_for_status(s):
        if s.status_code >= 400: e = requests.HTTPError(f"{s.status_code}"); e.response = s; raise e
def run(script):
    calls = []
    def post(url, **kw):
        m = re.search(r"models/([^:]+):", url).group(1); calls.append(m); return script(m, len(calls))
    llm.requests.post = post; llm.time.sleep = lambda x: None
    return real_ask("sys", "user"), calls
ok_body = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
out, calls = run(lambda m, n: Resp(200, ok_body) if m == "gemini-2.0-flash" else Resp(429, {"error": {"message": "quota"}})); print("  first two models rate-limited ->", repr(out), "| tried:", calls)
out, calls = run(lambda m, n: Resp(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})); print("  rejected key -> stops at once:", out, len(calls) == 1, "|", llm.LAST_ERROR[:60])
out, calls = run(lambda m, n: Resp(404, {"error": {"message": "model not found"}}) if n == 1 else Resp(200, ok_body)); print("  retired model -> next model:", repr(out), calls)
out, calls = run(lambda m, n: Resp(400, {"error": {"message": "thinking not supported"}}) if n == 1 else Resp(200, ok_body)); print("  model-specific 400 -> next model:", repr(out))
print("== 3. with the AI working: what it is given ==")
seen = {}; calls = []
def fake(system, user, *a, **k): seen["s"], seen["u"] = system, user; calls.append(1); return "- " + "\n- ".join(VENUES)
llm.ask = fake; a = rag.answer(bot, "list all the venues")
print("  asked to list everything:", ok("list ALL matching items" in seen["s"]), "| context has the first and the last venue (list spans several sections):", ok("Ikshaa Convention" in seen["u"] and "Heritage Courtyard" in seen["u"]))
rag.answer(bot, "just the names", history=hist); print("  follow-up gets the earlier question:", ok("which wedding venues" in seen["u"]))
print("== 4. answer cache ==")
calls.clear(); rag.answer(bot, "what is the price per plate"); rag.answer(bot, "what is the price per plate?"); n1 = len(calls)
db.run("insert into chunks(bot_id,source,text) values(?,?,?)", (bid, "extra", "new fact")); rag.answer(bot, "what is the price per plate"); print("  same question twice = 1 AI call:", ok(n1 == 1), "| knowledge changed -> asks again:", ok(len(calls) == 2))
print("== 5. dashboard status ==")
llm.ask = lambda *a, **k: "OK"; embed._post = lambda *a, **k: (_ for _ in ()).throw(type("E", (requests.HTTPError,), {})("x")) ; 
def bad(*a, **k): e = requests.HTTPError("403"); e.response = Resp(403, {"error": {"message": "API key not valid"}}); raise e
embed._post = bad; j = c.get("/api/ai/status", headers=H_).json(); print("  AI ok, smart search broken ->", j["ai"]["ok"], "|", j["embeddings"])
llm.ask = lambda *a, **k: None; llm.LAST_ERROR = "Gemini 403: API key not valid"; j = c.get("/api/ai/status", headers=H_).json(); print("  AI down -> ok:", j["ai"]["ok"], "|", j["ai"]["error"])
os.environ.pop("GEMINI_API_KEY"); print("  no key at all ->", llm.check()["error"][:70])
