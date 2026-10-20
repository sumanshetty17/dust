import os as _o; _o.environ["WEB_RESEARCH"] = "0"
import os, json, base64, threading, re
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
os.environ.update(DB_PATH="/tmp/g.db", GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="csecret", CRON_SECRET="cron123",
  GOOGLE_TOKEN_URL="http://127.0.0.1:8766/token", GMAIL_API_BASE="http://127.0.0.1:8766/gmail", GOOGLE_REVOKE_URL="http://127.0.0.1:8766/revoke")
if os.path.exists("/tmp/g.db"): os.remove("/tmp/g.db")
b64=lambda s:base64.urlsafe_b64encode(s.encode()).decode()
MSGS,LOG,DRAFTS,FLAGS={}, [], {}, {"bad_refresh":False}
def msg(i,frm,subj,body,extra=()):
    MSGS[i]={"id":i,"threadId":"T"+i,"payload":{"mimeType":"text/plain","body":{"data":b64(body)},"headers":[{"name":"From","value":frm},{"name":"Subject","value":subj},{"name":"Message-ID","value":f"<{i}@cust.test>"}]+[{"name":k,"value":v} for k,v in extra]}}
class H(BaseHTTPRequestHandler):
    def _go(s):
        n=int(s.headers.get("Content-Length",0)); raw=s.rfile.read(n).decode() if n else ""; p=urlparse(s.path).path; out={}; code=200
        j=lambda:json.loads(raw) if raw else {}
        if p=="/token":
            f=parse_qs(raw); LOG.append(("token",f["grant_type"][0]))
            if f["grant_type"][0]=="refresh_token":
                if FLAGS["bad_refresh"]: code,out=400,{"error":"invalid_grant"}
                else: out={"access_token":"AT2"}
            else: out={"access_token":"AT","refresh_token":"RT-secret"}
        elif p=="/revoke": LOG.append(("revoke",parse_qs(raw)["token"][0]))
        elif p=="/gmail/profile": out={"emailAddress":"owner@acme.test"}
        elif p=="/gmail/messages" and s.command=="GET": out={"messages":[{"id":k} for k in MSGS]}
        elif p.startswith("/gmail/messages/") and p.endswith("/modify"): LOG.append(("modify",p.split("/")[3],j()["addLabelIds"]))
        elif p=="/gmail/messages/send": LOG.append(("send",j())); out={"id":"sent"}
        elif p.startswith("/gmail/messages/"): out=MSGS[p.split("/")[3]]
        elif p=="/gmail/labels": out={"labels":[{"id":"INBOX","name":"INBOX"}]} if s.command=="GET" else {"id":"L_"+j()["name"]}
        elif p=="/gmail/drafts": d="D%d"%(len(DRAFTS)+1); DRAFTS[d]=j(); out={"id":d}
        elif p=="/gmail/drafts/send": LOG.append(("draft_send",j()["id"]))
        elif p.startswith("/gmail/drafts/"): LOG.append(("draft_delete",p.split("/")[3]))
        s.send_response(code); s.send_header("Content-Type","application/json"); s.end_headers(); s.wfile.write(json.dumps(out).encode())
    do_GET=do_POST=do_DELETE=_go
    def log_message(*a): pass
threading.Thread(target=HTTPServer(("127.0.0.1",8766),H).serve_forever,daemon=True).start()
import db, rag, llm, gmail, email as emaillib
llm.ask=lambda *a,**k:None
from fastapi.testclient import TestClient
from main import app
c=TestClient(app); ok=lambda x:"✅" if x else "❌"
t=c.post("/api/signup",json={"email":"o@acme.test","password":"password1"}).json()["token"]; H_={"Authorization":"Bearer "+t}
bid=c.post("/api/bots",json={"name":"Acme","site_url":"https://acme.test"},headers=H_).json()["id"]
rag.add_document(bid,"kb","We are open Monday to Saturday from 8am to 8pm. Closed on Sundays. Drain cleaning costs 800 rupees. Leak repair starts at 500 rupees.")
def decode(raw): return emaillib.message_from_bytes(base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)))
# --- OAuth
st=c.get(f"/api/bots/{bid}/gmail",headers=H_).json(); print("status before:",st)
url=c.post(f"/api/bots/{bid}/gmail/auth-url",headers=H_).json()["url"]; q=parse_qs(urlparse(url).query)
print("auth-url:",ok(q["client_id"]==["cid"] and q["access_type"]==["offline"] and q["prompt"]==["consent"] and q["redirect_uri"]==["https://testserver/api/gmail/callback"] and "gmail.modify" in q["scope"][0]))
print("bad state:",c.get("/api/gmail/callback?code=x&state=forged.sig").status_code,"| denied:",c.get("/api/gmail/callback?error=access_denied&state="+q["state"][0],follow_redirects=False).headers["location"])
r=c.get("/api/gmail/callback?code=abc&state="+q["state"][0],follow_redirects=False); print("callback ->",r.headers["location"])
row=db.one("select * from gmail_accounts where bot_id=?",(bid,)); print("token encrypted at rest:",ok(row["refresh_token"]!="RT-secret" and gmail.dec(row["refresh_token"])=="RT-secret"),"| email:",row["email"])
# --- Phase A: draft mode
msg("m1",'Priya <priya@cust.test>',"Opening hours?","What time are you open on Saturday?\n\nOn Mon, 1 Jan, Bob wrote:\n> old quoted text")
msg("m2",'Rohan <rohan@cust.test>',"Legal notice","I will contact my lawyer, this is unacceptable")
msg("m3",'Shop News <news@shop.test>',"Big sale!","Buy now",[("List-Unsubscribe","<mailto:x@y>")])
msg("m4",'noreply@bank.test',"Alert","Your statement is ready")
res=c.post(f"/api/bots/{bid}/gmail/sync",headers=H_).json(); print("A sync:",res)
d=decode(DRAFTS["D1"]["message"]["raw"]); body=d.get_payload(decode=True).decode()
print("A draft: to/subject/threading:",ok(d["To"]=="priya@cust.test" and d["Subject"]=="Re: Opening hours?" and d["In-Reply-To"]=="<m1@cust.test>" and DRAFTS["D1"]["message"]["threadId"]=="Tm1"),
      "| uses KB:",ok("Monday to Saturday" in body),"| AI footer:",ok("AI assistant" in body),"| quoted text stripped:",ok("old quoted" not in db.one("select body from emails where gmail_id='m1'")["body"]),"| no auto header:",ok(d["Auto-Submitted"] is None))
print("A labels:",[x for x in LOG if x[0]=="modify"],"| sent anything:",ok(not any(x[0]=="send" for x in LOG)))
print("A statuses:",{r["gmail_id"]:r["status"] for r in db.rows("select gmail_id,status from emails where bot_id=?",(bid,))})
print("A idempotent:",c.post(f"/api/bots/{bid}/gmail/sync",headers=H_).json()["checked"]==0)
# --- Phase B: auto mode + guards
c.post(f"/api/bots/{bid}/settings",json={"email_mode":"auto"},headers=H_)
msg("m5",'Alice <alice@cust.test>',"Price?","How much is drain cleaning?"); msg("m6",'Alice <alice@cust.test>',"Another","How much does leak repair cost?")
res=c.post(f"/api/bots/{bid}/gmail/sync",headers=H_).json(); print("B sync:",res)
sent=[x for x in LOG if x[0]=="send"]; sm=decode(sent[0][1]["raw"]); print("B auto-sent to alice:",ok(len(sent)==1 and sm["To"]=="alice@cust.test" and sm["Auto-Submitted"]=="auto-replied" and "800" in sm.get_payload(decode=True).decode()),
      "| 2nd mail from same sender -> draft (loop guard):",ok(res["drafts"]==1 and len(DRAFTS)==2))
# --- Phase C: owner approves / discards drafts
em=c.get(f"/api/bots/{bid}/emails",headers=H_).json(); dr={e["sender"]:e["id"] for e in em if e["status"]=="draft_saved"}; print("C pending drafts:",list(dr))
print("C send:",c.post(f"/api/bots/{bid}/emails/{dr['priya@cust.test']}/send",headers=H_).status_code,"| discard:",c.post(f"/api/bots/{bid}/emails/{dr['alice@cust.test']}/discard",headers=H_).status_code,
      "| again:",c.post(f"/api/bots/{bid}/emails/{dr['priya@cust.test']}/send",headers=H_).status_code,"|",[x for x in LOG if x[0].startswith("draft")])
# --- Phase D: cron, expired connection, disconnect, other user isolation
print("D cron:",c.get("/api/cron/gmail").status_code,c.get("/api/cron/gmail?secret=nope").status_code,c.get("/api/cron/gmail",headers={"Authorization":"Bearer cron123"}).json())
t2=c.post("/api/signup",json={"email":"x@evil.test","password":"password1"}).json()["token"]; print("D other user blocked:",c.post(f"/api/bots/{bid}/gmail/sync",headers={"Authorization":"Bearer "+t2}).status_code)
FLAGS["bad_refresh"]=True; r=c.post(f"/api/bots/{bid}/gmail/sync",headers=H_); print("D expired token:",r.status_code,r.json()["detail"][:60]); FLAGS["bad_refresh"]=False
c.post(f"/api/bots/{bid}/gmail/disconnect",headers=H_); print("D disconnect:",c.get(f"/api/bots/{bid}/gmail",headers=H_).json()["connected"],[x for x in LOG if x[0]=="revoke"])
