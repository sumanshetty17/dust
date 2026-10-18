"""Semantic embeddings via Google Gemini (free tier). Everything degrades gracefully to keyword search if unavailable."""
import os, base64, requests
import numpy as np
DIM = 384
MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
def available(): return bool(os.getenv("GEMINI_API_KEY"))
def _post(path, body):
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/" + path,
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}, json=body, timeout=45)
    r.raise_for_status(); return r.json()
def _norm(v):
    a = np.array(v, dtype=np.float32); n = np.linalg.norm(a); return a / (n or 1.0)
def enc(a): return base64.b64encode(a.astype(np.float16).tobytes()).decode()
def dec(s): return np.frombuffer(base64.b64decode(s), dtype=np.float16).astype(np.float32)
def docs(texts):
    """Raises on failure so the caller can report it. Returns list of encoded vectors."""
    m = "models/" + MODEL
    j = _post(m + ":batchEmbedContents", {"requests": [{"model": m, "content": {"parts": [{"text": t[:2000]}]},
              "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": DIM} for t in texts]})
    return [enc(_norm(e["values"])) for e in j["embeddings"]]
def query(text):
    """Returns a normalized vector, or None if embeddings are unavailable."""
    if not available(): return None
    try:
        m = "models/" + MODEL
        j = _post(m + ":embedContent", {"model": m, "content": {"parts": [{"text": text[:1000]}]},
                  "taskType": "RETRIEVAL_QUERY", "outputDimensionality": DIM})
        return _norm(j["embedding"]["values"])
    except Exception as e:
        print("embed query failed:", e); return None
