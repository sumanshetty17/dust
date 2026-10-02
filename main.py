import os, io, time, hashlib, hmac, secrets
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import db, rag, insights, email_assistant

try: db.init()
except Exception as e: print('DB init failed:', e)
DAILY_LIMIT = int(os.getenv('DAILY_CHAT_LIMIT', '500')); MAX_BOTS = int(os.getenv('MAX_BOTS_PER_USER', '3'))
app = FastAPI(title="SiteBot")
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

class Auth(BaseModel): email: str; password: str
class BotIn(BaseModel): name: str; site_url: str = ""
class TextIn(BaseModel): title: str = "Pasted text"; text: str
class UrlIn(BaseModel): url: str; max_pages: int = 25
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

@app.post("/api/bots")
def create_bot(b: BotIn, u=Depends(current_user)):
    if db.one("select count(*) n from bots where user_id=?", (u["id"],))["n"] >= MAX_BOTS: raise HTTPException(400, f"Free plan limit: {MAX_BOTS} bots")
    key = "pk_" + secrets.token_urlsafe(12)
    i = db.run("insert into bots(user_id,name,site_url,public_key) values(?,?,?,?)", (u["id"], b.name, b.site_url, key))
    return {"id": i, "public_key": key}
@app.get("/api/bots")
def list_bots(u=Depends(current_user)):
    return db.rows("select id,name,site_url,public_key,email_mode,(select count(*) from chunks where bot_id=bots.id) as chunks from bots where user_id=?", (u["id"],))
@app.post("/api/bots/{bot_id}/settings")
def settings(s: Settings, b=Depends(own_bot)):
    if s.email_mode not in ("draft", "auto"): raise HTTPException(400, "email_mode must be draft or auto")
    db.run("update bots set email_mode=? where id=?", (s.email_mode, b["id"])); return {"ok": True}

@app.post("/api/bots/{bot_id}/text")
def add_text(t: TextIn, b=Depends(own_bot)): return {"chunks": rag.add_document(b["id"], t.title, t.text)}
@app.post("/api/bots/{bot_id}/crawl")
def crawl(r: UrlIn, b=Depends(own_bot)):
    if not rag.safe_url(r.url): raise HTTPException(400, "URL must be a public http(s) address")
    return {"pages": rag.crawl(b["id"], r.url, min(r.max_pages, 25))}
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
def health(): return {"ok": True, "db": "postgres" if db.PG else "sqlite"}

@app.post("/api/chat/{public_key}")
def chat(public_key: str, c: ChatIn, request: Request):
    b = db.one("select * from bots where public_key=?", (public_key,))
    if not b: raise HTTPException(404, "Unknown bot")
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "x"); now = int(time.time())
    if db.one("select count(*) n from conversations where ip=? and ts>?", (ip, now - 60))["n"] >= 15: raise HTTPException(429, "Too many messages, slow down")
    if db.one("select count(*) n from conversations where bot_id=? and ts>?", (b["id"], now - 86400))["n"] >= DAILY_LIMIT: raise HTTPException(429, "Daily chat limit reached")
    msg = c.message.strip()[:1000]
    if not msg: raise HTTPException(400, "Empty message")
    hist = [m for m in c.history if isinstance(m, dict) and "role" in m and "content" in m]
    ans, ok, srcs = rag.answer(b, msg, hist)
    db.run("insert into conversations(bot_id,session,ip,ts,question,answer,answered) values(?,?,?,?,?,?,?)", (b["id"], c.session[:64], ip, now, msg, ans, int(ok)))
    return {"answer": ans, "answered": ok, "sources": srcs}

@app.get("/api/bots/{bot_id}/insights")
def get_insights(b=Depends(own_bot)):
    t = insights.topics(b["id"]); st = db.one("select count(*) n, coalesce(sum(1-answered),0) u from conversations where bot_id=?", (b["id"],))
    gaps = db.rows("select min(question) question, count(*) n from conversations where bot_id=? and answered=0 group by lower(question) order by n desc limit 15", (b["id"],))
    return {"total": int(st["n"]), "unanswered": int(st["u"]), "topics": t[:12], "gaps": gaps, "summary": insights.summary(b["id"])}
@app.get("/api/bots/{bot_id}/conversations")
def convs(b=Depends(own_bot)): return db.rows("select question,answer,answered,created from conversations where bot_id=? order by id desc limit 100", (b["id"],))
@app.post("/api/bots/{bot_id}/emails/process")
def process_email(e: EmailIn, b=Depends(own_bot)): return email_assistant.handle(b, e.sender, e.subject, e.body)
@app.get("/api/bots/{bot_id}/emails")
def list_emails(b=Depends(own_bot)): return db.rows("select id,sender,subject,category,reason,reply,status,created from emails where bot_id=? order by id desc limit 100", (b["id"],))

@app.get("/widget.js")
def widget(): return FileResponse(os.path.join(HERE, "static/widget.js"), media_type="application/javascript")
@app.get("/")
def home(): return FileResponse(os.path.join(HERE, "static/dashboard.html"))
