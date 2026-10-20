"""Background research about the business behind a website: what it does, services, history, locations, reputation.
Done with live web search, stored per assistant, and used only to fill gaps the website itself doesn't answer."""
import os, re, json, time
from urllib.parse import urlparse
import db, llm

def _on(bot): return os.getenv("WEB_RESEARCH", "1") != "0" and bot.get("use_research") in (1, None, True)
def enabled_for(bot_id):
    b = db.one("select * from bots where id=?", (bot_id,)); return bool(b) and _on(b)
def summary(bot_id):
    r = db.one("select summary from research where bot_id=? and status=?", (bot_id, "done")); return (r["summary"] or "") if r else ""
def status(bot_id):
    r = db.one("select status from research where bot_id=?", (bot_id,)); return r["status"] if r else ""
def sources(bot_id):
    r = db.one("select sources from research where bot_id=?", (bot_id,))
    try: return json.loads(r["sources"]) if r and r["sources"] else []
    except Exception: return []

def _clean(t):  # web text is untrusted: no control characters, bounded size
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t or ""); return re.sub(r"\n{3,}", "\n\n", t).strip()[:4500]

def _prompt(bot):
    url = bot["site_url"] or ""; host = urlparse(url if "//" in url else "//" + url).netloc.removeprefix("www.")
    return (f"Research the business that owns the website {url} (called \"{bot['name']}\"). Use web search; search for its name and for {host}.\n"
            "Write a factual briefing with exactly these headings:\nOVERVIEW (what the business does and who it serves)\nPRODUCTS AND SERVICES\n"
            "HISTORY AND FOUNDING (when it started, founders, key milestones)\nLOCATIONS AND AREAS SERVED\nCUSTOMERS AND REPUTATION (notable clients, awards, press, review ratings)\nOTHER USEFUL FACTS\n"
            f"Rules: include only facts you can attribute to THIS business, the one at {host}. If another company has a similar name, ignore it. "
            "If you cannot find something, write 'Not found' under that heading. Never guess. Do not include prices unless the business publishes them. Maximum 450 words.")

def _save(bot_id, st, text="", srcs=None, err="", started=None):
    now = int(time.time()); db.run("delete from research where bot_id=?", (bot_id,))
    db.run("insert into research(bot_id,status,summary,sources,updated,started,error) values(?,?,?,?,?,?,?)", (bot_id, st, text, json.dumps(srcs or []), now, started or now, err[:200]))

def run(bot_id, force=False):
    """Returns the resulting status: done / failed / running / off. Never raises."""
    try:
        bot = db.one("select * from bots where id=?", (bot_id,))
        if not bot: return "missing"
        if not _on(bot): return "off"
        row, now = db.one("select * from research where bot_id=?", (bot_id,)), int(time.time())
        if row and not force:
            if row["status"] == "running" and now - (row["started"] or 0) < 120: return "running"
            if row["status"] == "done" and now - (row["updated"] or 0) < 30 * 86400: return "done"
            if row["status"] == "failed" and now - (row["updated"] or 0) < 3600: return "failed"  # don't hammer after a failure
        _save(bot_id, "running", started=now)
        text, srcs = llm.research(_prompt(bot)); text = _clean(text)
        if len(text) < 80 or len(re.findall(r"not found", text, re.I)) >= 5: _save(bot_id, "failed", err=llm.LAST_ERROR or "Nothing reliable found"); return "failed"
        _save(bot_id, "done", text, srcs); return "done"
    except Exception as e:
        print("research failed:", type(e).__name__, e)
        try: _save(bot_id, "failed", err=str(e))
        except Exception: pass
        return "failed"
