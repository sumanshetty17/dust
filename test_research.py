import os, re, time, threading
os.environ.update(DB_PATH="/tmp/rs.db", CRON_SECRET="cron123"); os.environ.pop("ANTHROPIC_API_KEY", None); os.environ["GEMINI_API_KEY"] = "fake"
if "DATABASE_URL" not in os.environ and os.path.exists("/tmp/rs.db"): os.remove("/tmp/rs.db")
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from types import SimpleNamespace as NS
LOREM = " ".join(["We help couples book wedding venues, decorators and photographers across Bangalore."] * 5)
SITE = {"/": f"<html><head><title>The Wedding Company</title></head><body><header><nav><a href='/venues'>Venues</a></nav></header><main><p>Welcome. {LOREM}</p></main></body></html>",
        "/venues": f"<html><head><title>Venues</title></head><body><main><p>Browse venues. {LOREM}</p></main></body></html>"}
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        time.sleep(0.3); b = SITE.get(urlparse(s.path).path)
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type", "text/html"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", 8781), H).serve_forever, daemon=True).start()
import rag, llm, research, db, requests
rag.safe_url = lambda u: True; real_research = llm.research; llm.ask = lambda *a, **k: None
from fastapi.testclient import TestClient
from main import app
c = TestClient(app); ok = lambda x: "✅" if x else "❌"
print("== 1. the web-search request ==")
BRIEF = "OVERVIEW\nThe Wedding Company is a venue-booking platform based in Bengaluru.\nHISTORY AND FOUNDING\nFounded in 2018 and has since helped thousands of couples book venues across India.\nPRODUCTS AND SERVICES\nVenue booking, decor, photography.\n" * 1
class Resp:
    def __init__(s, code, body): s.status_code, s._b = code, body
    def json(s): return s._b
    def raise_for_status(s):
        if s.status_code >= 400: e = requests.HTTPError(str(s.status_code)); e.response = s; raise e
sent = {}
def post(url, **kw): sent["url"], sent["json"] = url, kw["json"]; return Resp(200, {"candidates": [{"content": {"parts": [{"text": BRIEF}]}, "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://x.test/a", "title": "thewedding.company"}}, {"web": {"uri": "https://x.test/a", "title": "dup"}}]}}]})
llm.requests.post = post; text, srcs = real_research("Research X"); print("  Gemini: uses Google Search grounding:", ok(sent["json"]["tools"] == [{"google_search": {}}]), "| text:", ok("Founded in 2018" in text), "| sources de-duplicated:", srcs)
os.environ["ANTHROPIC_API_KEY"] = "k"; seen = {}
class FakeClient:
    class messages:
        @staticmethod
        def create(**kw): seen.update(kw); return NS(content=[NS(type="text", text=BRIEF, citations=[NS(url="https://y.test", title="Y")]), NS(type="server_tool_use")])
llm._client = FakeClient; text, srcs = real_research("Research X"); print("  Claude: uses the web search tool:", ok(seen["tools"][0]["name"] == "web_search"), "|", srcs); os.environ.pop("ANTHROPIC_API_KEY"); llm._client = None; llm.requests.post = requests.post
print("== 2. runs in parallel with reading the site; the user sees nothing extra ==")
calls, times = [], {}
def fake_research(prompt, max_tokens=1400): calls.append(prompt); times["rs"] = time.time(); time.sleep(0.8); times["re"] = time.time(); return BRIEF, [{"title": "t", "url": "https://x.test"}]
llm.research = fake_research; orig_crawl = rag.crawl
def crawl(*a, **k): times["cs"] = time.time(); r = orig_crawl(*a, **k); times["ce"] = time.time(); return r
rag.crawl = crawl
t = c.post("/api/signup", json={"email": "o@x.test", "password": "password1"}).json()["token"]; H_ = {"Authorization": "Bearer " + t}
t0 = time.time(); r = c.post("/api/bots/quick", json={"url": "http://127.0.0.1:8781"}, headers=H_).json(); bid, key = r["id"], r["public_key"]; took = time.time() - t0
print(f"  overlapped with reading: {ok(times['rs'] < times['ce'] and times['cs'] < times['re'])} | total {took:.1f}s | response has no research fields:", ok("research" not in str(r).lower()), "| stored:", research.status(bid))
print("  prompt names the business and its domain:", ok("127.0.0.1:8781" in calls[0] and "THIS business" in calls[0]), "| asks for history/founding:", ok("HISTORY AND FOUNDING" in calls[0]))
print("== 3. used when answering ==")
bot = db.one("select * from bots where id=?", (bid,)); seen = {}
def fake_ask(system, user, *a, **k): seen["s"], seen["u"] = system, user; return "It was founded in 2018."
llm.ask = fake_ask; a = rag.answer(bot, "from when this comoany is excited?", [{"role": "user", "content": "what do you do"}])
print("  briefing is in the AI's input:", ok("<web_research>" in seen["u"] and "Founded in 2018" in seen["u"]), "| website text is still used for website questions:", ok((rag.answer(bot, "do you book venues"), "Browse venues" in seen["u"] or "We help couples" in seen["u"])[1]))
print("  rules: web notes only for gaps, never prices/policies, trust the website:", ok("Never use it for prices" in seen["s"] and "trust the website" in seen["s"]), "| answer:", a[0])
print("== 4. failures never block anything ==")
db.run("delete from research where bot_id=?", (bid,)); calls.clear(); llm.research = lambda *a, **k: (None, []); llm.LAST_ERROR = "Gemini web search 429: quota"
print("  search unavailable ->", research.run(bid), "| site still answers:", ok(rag.answer(bot, "venues")[1]), "| no retry within the hour:", end=" ")
n = [0]; llm.research = lambda *a, **k: (n.__setitem__(0, n[0] + 1) or (BRIEF, [])); research.run(bid); print(ok(n[0] == 0), "| forced retry works:", research.run(bid, force=True))
llm.research = lambda *a, **k: ("Not found\n" * 8 + "x" * 60, []); print("  'Not found' everywhere ->", research.run(bid, force=True))
llm.research = lambda *a, **k: ("OVERVIEW\x00\x07 " + "A" * 9000, []); research.run(bid, force=True); s = research.summary(bid); print("  untrusted text: control chars removed:", ok("\x00" not in s and "\x07" not in s), "| capped:", len(s))
db.run("update research set status=?, started=? where bot_id=?", ("running", int(time.time()), bid)); print("  already running -> skipped:", research.run(bid))
print("== 5. dashboard side ==")
llm.research = fake_research; db.run("delete from research where bot_id=?", (bid,))
print("  quiet completion call:", c.post(f"/api/bots/{bid}/research", headers=H_).json(), "| bots list:", [(b["research_status"], b["use_research"]) for b in c.get("/api/bots", headers=H_).json()], "| listed as a source:", ok("Public web research about your business" in [x["source"] for x in c.get(f"/api/bots/{bid}/sources", headers=H_).json()]))
c.post(f"/api/bots/{bid}/research/setting", json={"enabled": False}, headers=H_); seen.clear(); rag.answer(bot, "when was it founded", [])
print("  switched off: briefing deleted:", ok(research.summary(bid) == ""), "| not in the prompt:", ok("Founded in 2018" not in seen["u"]), "| run ->", research.run(bid, force=True))
c.post(f"/api/bots/{bid}/research/setting", json={"enabled": True}, headers=H_); print("  switched on again ->", research.run(bid))
print("== 6. monthly refresh by the scheduler ==")
calls.clear(); db.run("update research set updated=? where bot_id=?", (int(time.time()) - 31 * 86400, bid)); r = c.get("/api/cron/relearn", headers={"Authorization": "Bearer cron123"}).json()
print("  stale briefing refreshed:", ok(len(calls) == 1), r["relearned"][:1], "| fresh one left alone:", ok(not c.get("/api/cron/relearn", headers={"Authorization": "Bearer cron123"}).json()["relearned"]))
os.environ["WEB_RESEARCH"] = "0"; print("  WEB_RESEARCH=0 switches the feature off globally ->", research.run(bid, force=True))
