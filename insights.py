import math
from collections import Counter
import db, llm, rag

def _cos(a, b):
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0

def topics(bot_id, limit=2000, threshold=0.45):
    rows = db.rows("select question,answered from conversations where bot_id=? order by id desc limit ?", (bot_id, limit))
    clusters = []  # each: centroid Counter + member indexes
    vecs = []
    for i, r in enumerate(rows):
        v = Counter(rag.tokens(r["question"]) or [r["question"].lower()]); vecs.append(v)
        best, bs = None, 0
        for c in clusters:
            s = _cos(v, c["cen"])
            if s > bs: best, bs = c, s
        if best is not None and bs >= threshold: best["ids"].append(i); best["cen"].update(v)
        else: clusters.append({"cen": Counter(v), "ids": [i]})
    out = []
    for c in clusters:
        rep = max(c["ids"], key=lambda i: _cos(vecs[i], c["cen"]))
        out.append(dict(topic=rows[rep]["question"], count=len(c["ids"]),
                        unanswered=sum(1 for i in c["ids"] if not rows[i]["answered"]),
                        examples=[rows[i]["question"] for i in c["ids"][:4]]))
    return sorted(out, key=lambda t: -t["count"])

def summary(bot_id):
    t = topics(bot_id)
    if not t: return "No conversations yet."
    total = sum(x["count"] for x in t); top = t[:5]
    facts = "\n".join(f"- {x['topic']} ({x['count']} asks, {x['unanswered']} unanswered)" for x in top)
    out = llm.ask("You write short, practical weekly briefings for a business owner about what their customers struggle with. "
                  "Give 3 bullet insights and 2 recommended actions. No fluff.", f"Total questions: {total}\nTop topics:\n{facts}")
    return out or f"{total} questions so far. Most common: {top[0]['topic']} ({top[0]['count']} times)."
