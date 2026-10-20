"""AI provider: Anthropic Claude if ANTHROPIC_API_KEY is set, else Google Gemini (free tier) if GEMINI_API_KEY is set.
Gemini is tried across several models: free-tier limits are per model, so a rate limit on one falls through to the next.
ask() returns None when nothing works; LAST_ERROR then says why (shown in the dashboard)."""
import os, time, requests
_client = None
LAST_ERROR = ""
DEFAULT_MODELS = "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.0-flash"

def provider(): return "claude" if os.getenv("ANTHROPIC_API_KEY") else ("gemini" if os.getenv("GEMINI_API_KEY") else None)
def available(): return provider() is not None

def _claude(system, user, max_tokens):
    global _client
    import anthropic
    _client = _client or anthropic.Anthropic()
    r = _client.messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens,
                                system=system, messages=[{"role": "user", "content": user}])
    return r.content[0].text.strip()

def _gemini(system, user, max_tokens, model):
    cfg = {"maxOutputTokens": max_tokens if "2.5" in model else max(max_tokens, 1500), "temperature": 0.2}
    if "2.5" in model: cfg["thinkingConfig"] = {"thinkingBudget": 0}  # keep the whole budget for the answer
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": cfg}, timeout=25)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

def _msg(e):
    try: return e.response.json()["error"]["message"][:160]
    except Exception: return (str(e) or "")[:160]

def ask(system, user, max_tokens=700):
    """Returns text, or None if no key / every model failed (see LAST_ERROR)."""
    global LAST_ERROR
    if os.getenv("ANTHROPIC_API_KEY"):
        try: out = _claude(system, user, max_tokens); LAST_ERROR = ""; return out
        except Exception as e: LAST_ERROR = "Claude: " + str(e)[:150]; print("LLM error:", LAST_ERROR)
    if os.getenv("GEMINI_API_KEY"):
        models = [m.strip() for m in (os.getenv("GEMINI_MODELS") or os.getenv("GEMINI_MODEL", "") + "," + DEFAULT_MODELS).split(",") if m.strip()]
        for model in dict.fromkeys(models):
            for attempt in range(2):
                try: out = _gemini(system, user, max_tokens, model); LAST_ERROR = ""; return out
                except requests.HTTPError as e:
                    code = e.response.status_code if e.response is not None else 0; msg = _msg(e); LAST_ERROR = f"Gemini {code}: {msg}"; print("LLM error:", model, LAST_ERROR)
                    if code in (401, 403) or (code == 400 and "api key" in msg.lower()): return None  # the key itself is the problem: other models would fail too
                    if code in (429, 500, 503) and attempt == 0: time.sleep(1.2); continue  # brief pause, retry once, then try the next model
                    break
                except Exception as e: LAST_ERROR = "Gemini: " + str(e)[:150]; print("LLM error:", model, LAST_ERROR); break
        return None
    LAST_ERROR = "No AI key is set. Add GEMINI_API_KEY in Vercel."; return None

def check():
    """Used by the dashboard to show whether the AI is really working."""
    global LAST_ERROR
    if not available(): return dict(provider=None, ok=False, error="No AI key is set. Add GEMINI_API_KEY in Vercel → Settings → Environment Variables, then redeploy.")
    LAST_ERROR = ""; out = ask("Reply with the single word OK.", "ping", 20)
    return dict(provider=provider(), ok=out is not None, error="" if out is not None else (LAST_ERROR or "The AI did not respond."))

RESEARCH_MODELS = "gemini-2.5-flash,gemini-2.0-flash"
def _dedupe(srcs):
    out, seen = [], set()
    for s in srcs:
        if s.get("url") and s["url"] not in seen: seen.add(s["url"]); out.append(s)
    return out

def research(prompt, max_tokens=1400):
    """Answer a question using live web search. Claude: web search tool. Gemini: Google Search grounding.
    Returns (text, sources) or (None, []) when unavailable (then SiteBot simply works from the website alone)."""
    global LAST_ERROR, _client
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            _client = _client or anthropic.Anthropic()
            r = _client.messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}], messages=[{"role": "user", "content": prompt}])
            text = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text").strip(); srcs = []
            for b in r.content:
                for ci in (getattr(b, "citations", None) or []):
                    if getattr(ci, "url", None): srcs.append({"title": getattr(ci, "title", "") or ci.url, "url": ci.url})
            LAST_ERROR = ""; return (text or None), _dedupe(srcs)
        except Exception as e: LAST_ERROR = "Claude web search: " + str(e)[:150]; print("research error:", LAST_ERROR)
    if os.getenv("GEMINI_API_KEY"):
        for model in RESEARCH_MODELS.split(","):
            try:
                cfg = {"maxOutputTokens": max_tokens, "temperature": 0.1}
                if "2.5" in model: cfg["thinkingConfig"] = {"thinkingBudget": 0}
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                    json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}], "generationConfig": cfg}, timeout=45)
                r.raise_for_status(); cand = r.json()["candidates"][0]
                text = "".join(p.get("text", "") for p in cand["content"]["parts"]).strip()
                srcs = [{"title": g["web"].get("title", ""), "url": g["web"].get("uri", "")} for g in (cand.get("groundingMetadata", {}).get("groundingChunks") or []) if "web" in g]
                LAST_ERROR = ""; return (text or None), _dedupe(srcs)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0; msg = _msg(e); LAST_ERROR = f"Gemini web search {code}: {msg}"; print("research error:", model, LAST_ERROR)
                if code in (401, 403) and "api key" in msg.lower(): return None, []
            except Exception as e: LAST_ERROR = "Gemini web search: " + str(e)[:150]; print("research error:", model, LAST_ERROR)
    return None, []
