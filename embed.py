"""Semantic embeddings via Google Gemini (free tier). Everything degrades gracefully to keyword search if unavailable."""
import os, base64, requests
import numpy as np
DIM = 384
MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
LAST_ERROR = ""
def available(): return bool(os.getenv("GEMINI_API_KEY"))
def _post(path, body):
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/" + path,
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}, json=body, timeout=45)
    r.raise_for_status(); return r.json()
def _msg(e):
    try: return e.response.json()["error"]["message"][:160]
    except Exception: return (str(e) or "")[:160]
def _norm(v):
    a = np.array(v, dtype=np.float32); n = np.linalg.norm(a); return a / (n or 1.0)
def enc(a): return base64.b64encode(a.astype(np.float16).tobytes()).decode()
def dec(s): return np.frombuffer(base64.b64decode(s), dtype=np.float16).astype(np.float32)
def docs(texts):
    """Raises on failure so the caller can report it. Returns list of encoded vectors."""
    global LAST_ERROR
    m = "models/" + MODEL
    try:
        j = _post(m + ":batchEmbedContents", {"requests": [{"model": m, "content": {"parts": [{"text": t[:2000]}]},
                  "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": DIM} for t in texts]})
        LAST_ERROR = ""; return [enc(_norm(e["values"])) for e in j["embeddings"]]
    except Exception as e: LAST_ERROR = _msg(e); raise
def query(text):
    """Returns a normalized vector, or None if embeddings are unavailable."""
    global LAST_ERROR
    if not available(): return None
    try:
        m = "models/" + MODEL
        j = _post(m + ":embedContent", {"model": m, "content": {"parts": [{"text": text[:1000]}]},
                  "taskType": "RETRIEVAL_QUERY", "outputDimensionality": DIM})
        LAST_ERROR = ""; return _norm(j["embedding"]["values"])
    except Exception as e:
        LAST_ERROR = _msg(e); print("embed query failed:", LAST_ERROR); return None
def check():
    if not available(): return dict(ok=False, error="No GEMINI_API_KEY is set, so smart (meaning-based) search is off.")
    try: docs(["ping"]); return dict(ok=True, error="")
    except Exception: return dict(ok=False, error=LAST_ERROR or "Embedding request failed.")
