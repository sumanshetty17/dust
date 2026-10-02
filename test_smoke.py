import os; os.environ["DB_PATH"]="/tmp/t.db"
if os.path.exists("/tmp/t.db"): os.remove("/tmp/t.db")
from fastapi.testclient import TestClient
from main import app
c=TestClient(app)
t=c.post("/api/signup",json={"email":"a@b.com","password":"password1"}).json()["token"]; H={"Authorization":"Bearer "+t}
b=c.post("/api/bots",json={"name":"Acme","site_url":"https://acme.com"},headers=H).json()
print(c.post(f"/api/bots/{b['id']}/text",json={"text":"Refund policy: you can return any product within 30 days for a full refund. Shipping takes 3 to 5 business days across India. Support is available Monday to Friday 9am to 6pm. We accept UPI, credit cards and net banking."},headers=H).json())
for q in ["how do i get a refund","what is the refund policy","how long does shipping take","do you sell spaceships"]:
    print(q,"->",c.post(f"/api/chat/{b['public_key']}",json={"message":q}).json()["answered"])
i=c.get(f"/api/bots/{b['id']}/insights",headers=H).json(); print(i["total"],i["unanswered"],[(x["topic"],x["count"]) for x in i["topics"]])
print(c.post(f"/api/bots/{b['id']}/emails/process",json={"sender":"x@y.com","subject":"Refund","body":"how long does shipping take?"},headers=H).json()["category"])
print(c.post(f"/api/bots/{b['id']}/emails/process",json={"sender":"x@y.com","subject":"Legal","body":"I will contact my lawyer, this is unacceptable"},headers=H).json()["category"])
print(c.get("/").status_code, c.get("/widget.js").status_code, c.get("/api/bots").status_code)
