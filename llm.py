"""LLM provider: Anthropic Claude if ANTHROPIC_API_KEY is set, else free Google Gemini if GEMINI_API_KEY is set.
If neither works, returns None and callers fall back to plain retrieval answers."""
import os, requests
_client = None

def available(): return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY"))

def _claude(system, user, max_tokens):
    global _client
    import anthropic
    _client = _client or anthropic.Anthropic()
    r = _client.messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens,
                                system=system, messages=[{"role": "user", "content": user}])
    return r.content[0].text.strip()

def _gemini(system, user, max_tokens):
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
        json={"system_instruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}}, timeout=40)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

def ask(system, user, max_tokens=600):
    """Returns text, or None if no key / call fails (e.g. free-tier rate limit)."""
    try:
        if os.getenv("ANTHROPIC_API_KEY"): return _claude(system, user, max_tokens)
        if os.getenv("GEMINI_API_KEY"): return _gemini(system, user, max_tokens)
    except Exception as e:
        print("LLM error:", e)
    return None
