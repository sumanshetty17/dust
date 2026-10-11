"""Client for the optional SiteBot Reader service (reads JavaScript-heavy sites with a real browser)."""
import os, requests
def configured(): return bool(os.getenv("READER_URL") and os.getenv("READER_KEY"))
def _h(): return {"X-Reader-Key": os.getenv("READER_KEY", "")}
def _u(p): return os.getenv("READER_URL", "").rstrip("/") + p
def start(url, max_pages=30, render="auto", callback=""):
    r = requests.post(_u("/jobs"), json={"url": url, "max_pages": max_pages, "render": render, **({"callback": callback} if callback else {})}, headers=_h(), timeout=55)  # long timeout: free hosts sleep
    r.raise_for_status(); return r.json()["job"]
def status(job):
    r = requests.get(_u("/jobs/" + job), headers=_h(), timeout=55)
    if r.status_code == 404: return {"status": "error", "error": "The reader restarted and lost this job. Please start again."}
    r.raise_for_status(); return r.json()
