import os
_client = None
def available(): return bool(os.getenv("ANTHROPIC_API_KEY"))
def ask(system, user, max_tokens=600):
    """Returns text, or None if no API key / call fails (callers must have a fallback)."""
    global _client
    if not available(): return None
    try:
        import anthropic
        _client = _client or anthropic.Anthropic()
        r = _client.messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
            max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
        return r.content[0].text.strip()
    except Exception as e:
        print("LLM error:", e); return None
