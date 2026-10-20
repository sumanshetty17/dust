import os as _o; _o.environ["WEB_RESEARCH"] = "0"
import os, threading, hashlib, re; os.environ["DB_PATH"]="/tmp/t.db"
if os.path.exists("/tmp/t.db"): os.remove("/tmp/t.db")
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np
PAGES={"/":"<title>Acme Plumbing | Home</title><meta name=description content='Acme Plumbing: fast, friendly plumbers in Pune since 2008.'><header><nav><a href=/>Home</a><a href=/pricing>Pricing</a><a href=/account/settings aria-label='Settings'><img alt=''></a></nav></header><h1>Acme Plumbing</h1><p>We fix leaks, blocked drains and water heaters across Pune.</p><a href=/services>Services</a><a href=/pricing>Pricing</a><a href=/contact>Contact</a><footer>Call us: +91 98765 43210 <a href='mailto:help@acme.test'>help@acme.test</a></footer>",
"/services":"<title>Services</title><h1>Our services</h1><p>Drain cleaning, leak repair, water heater installation, bathroom fittings and emergency plumbing available 24/7.</p><footer>Call us: +91 98765 43210</footer>",
"/pricing":"<title>Pricing</title><h1>Pricing</h1><p>Drain cleaning costs 800 rupees. Leak repair starts at 500 rupees. Water heater installation is 1500 rupees. There is no call-out fee.</p>",
"/contact":"<title>Contact</title><h1>Opening hours</h1><p>We are open Monday to Saturday from 8am to 8pm. Closed on Sundays. Visit us at 12 MG Road, Pune.</p>",
"/sitemap.xml":"<urlset><url><loc>http://127.0.0.1:8765/faq</loc></url></urlset>",
"/faq":"<title>FAQ</title><h1>FAQ</h1><p>Do you offer warranty? Yes, every repair carries a 6 month warranty.</p>"}
class H(BaseHTTPRequestHandler):
    def do_GET(s):
        b=PAGES.get(s.path.split("?")[0]); 
        if b is None: s.send_response(404); s.end_headers(); return
        s.send_response(200); s.send_header("Content-Type","application/xml" if "xml" in s.path else "text/html"); s.end_headers(); s.wfile.write(b.encode())
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1",8765),H).serve_forever,daemon=True).start()
import embed, rag
rag.safe_url=lambda u:True
def hv(t):
    v=np.zeros(384,dtype=np.float32)
    for w in rag.tokens(t): v[int(hashlib.md5(w.encode()).hexdigest(),16)%384]+=1
    return v/(np.linalg.norm(v) or 1)
os.environ["GEMINI_API_KEY"]="fake"
embed.docs=lambda ts:[embed.enc(hv(t)) for t in ts]; embed.query=lambda t:hv(t)
import llm; llm.ask=lambda *a,**k:None   # no LLM here: tests retrieval + fallback
from fastapi.testclient import TestClient
from main import app
c=TestClient(app)
t=c.post("/api/signup",json={"email":"a@b.com","password":"password1"}).json()["token"]; H_={"Authorization":"Bearer "+t}
r=c.post("/api/bots/quick",json={"url":"http://127.0.0.1:8765"},headers=H_).json(); print("quick:",{k:r[k] for k in("pages","title","warning")})
bid=r["id"]; key=r["public_key"]
print("embed:",c.post(f"/api/bots/{bid}/embed",headers=H_).json())
print("sources:",[s["source"].replace("http://127.0.0.1:8765","") for s in c.get(f"/api/bots/{bid}/sources",headers=H_).json()])
prof=[x for x in __import__("db").rows("select text from chunks where bot_id=? and source='site-profile'",(bid,))][0]["text"]
print("profile has phone/email/about:", "98765" in prof, "help@acme.test" in prof, "Pune since 2008" in prof)
for q,exp in [("how much is drain cleaning","800"),("when are you open","Monday to Saturday"),("is there a warranty on repairs","6 month"),("do you sell spaceships","")]:
    a=c.post(f"/api/chat/{key}",json={"message":q}).json(); print(q,"->",a["answered"], (exp in a["answer"]) if exp else "")
print("bot name:",[b["name"] for b in c.get("/api/bots",headers=H_).json()])
print("demo/health/dash:",c.get(f"/demo/{key}").status_code,c.get("/demo/nope").status_code,c.get("/").status_code)
r2=c.post(f"/api/bots/{bid}/crawl",json={"url":"http://127.0.0.1:8765"},headers=H_).json(); print("recrawl:",r2["pages"],"chunks now:",c.get("/api/bots",headers=H_).json()[0]["chunks"])

print("--- navigation ---")
print("menu learned:",[m["label"] for m in c.get(f"/api/bots/{bid}/nav",headers=H_).json()])
a=c.post(f"/api/chat/{key}",json={"message":"where is the settings"}).json(); print("rule-based:",a["answered"],a["actions"])
print("guide add:",c.post(f"/api/bots/{bid}/guide",json={"title":"Billing","steps":"Click your photo at the top right, then Billing.","url":"/account/billing","target":"Billing"},headers=H_).status_code,
      c.post(f"/api/bots/{bid}/guide",json={"title":"x","url":"javascript:alert(1)"},headers=H_).status_code)
a=c.post(f"/api/chat/{key}",json={"message":"how do i change billing"}).json(); print("guide answer:",a["answer"][:50],a["actions"])
def fake(system,user,*a,**k):
    n=re.search(r"D(\d+): Settings",user).group(1); return f"Click the gear icon. [[GO:{n}]] [[GO:99]]"
llm.ask=fake; rag.llm.ask=fake
a=c.post(f"/api/chat/{key}",json={"message":"where do I find my settings"}).json(); print("llm tags:",a["answer"],a["actions"])

llm.ask=lambda *a,**k:None
print("--- v3 features ---")
r=c.post(f"/api/chat/{key}",json={"message":"do you sell spaceships"}).json(); print("handoff flag:",r["handoff"],"| id:",bool(r["id"]))
print("feedback:",c.post(f"/api/chat/{key}/feedback",json={"id":r["id"],"helpful":-1}).status_code,c.post(f"/api/chat/{key}/feedback",json={"id":r["id"],"helpful":5}).status_code)
i=c.get(f"/api/bots/{bid}/insights",headers=H_).json(); print("insights feedback:",i["feedback"],"bad:",[x["question"] for x in i["bad"]])
print("lead:",c.post(f"/api/chat/{key}/lead",json={"email":"nope"}).status_code,c.post(f"/api/chat/{key}/lead",json={"name":"Asha","email":"asha@x.com","question":"spaceships?"}).status_code,[x["email"] for x in c.get(f"/api/bots/{bid}/leads",headers=H_).json()])
print("appearance:",c.post(f"/api/bots/{bid}/appearance",json={"title":"Acme Help","color":"#e11d48","greeting":"Hello!","domain_lock":True,"allowed_domains":"https://www.Acme.test/, shop.acme.test"},headers=H_).json(),c.post(f"/api/bots/{bid}/appearance",json={"color":"red"},headers=H_).status_code)
print("widget cfg:",c.get(f"/api/widget/{key}").json())
post=lambda o:c.post(f"/api/chat/{key}",json={"message":"opening hours"},headers={"Origin":o}).status_code
print("lock -> evil:",post("https://evil.com"),"| acme:",post("https://www.acme.test"),"| sub:",post("https://shop.acme.test"),"| site host:",post("http://127.0.0.1:8765"),"| none:",c.post(f"/api/chat/{key}",json={"message":"x"}).status_code,"| lead from evil:",c.post(f"/api/chat/{key}/lead",json={"email":"a@b.co"},headers={"Origin":"https://evil.com"}).status_code)
print("verify before:",c.post(f"/api/bots/{bid}/verify",headers=H_).json()["installed"]); PAGES["/"]+=f'<script data-key="{key}"></script>'
print("verify after:",c.post(f"/api/bots/{bid}/verify",headers=H_).json()["installed"])
print("bots fields:",{k:v for k,v in c.get("/api/bots",headers=H_).json()[0].items() if k in("color","title","domain_lock","allowed_domains")})
