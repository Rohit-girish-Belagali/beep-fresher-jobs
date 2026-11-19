"""LLM tagging with Claude Haiku 5.5: role, city, job type, fresher-suitability.

* Batches of BATCH posts per request (system prompt + taxonomy is shared overhead, so it amortises).
* Results are cached on disk by content hash -> a daily run only pays for posts it has not seen.
* Every call's token usage is logged to data/usage.jsonl so cost/1000 posts is measured, not guessed.
"""
import hashlib
import json
import os
import re
import time

def _load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


_load_env()
USE_OR = bool(os.environ.get("OPENROUTER_API_KEY"))
MODEL = os.environ.get("TAG_MODEL", "anthropic/claude-haiku-5.5" if USE_OR else "claude-haiku-5-5")
PRICE_IN, PRICE_OUT = 0.10, 0.50          # USD per 1M tokens, Haiku 5.5 (prompts <=100K tokens)
BATCH = 8

ROLES = ["Software Engineering", "Data & Analytics", "AI / ML", "Product Management", "Design / UX",
         "Marketing & Growth", "Sales & Business Development", "Operations & Supply Chain",
         "Finance & Accounting", "HR & Recruiting", "Customer Support / Success", "Content & Writing",
         "Hardware / Electrical / Mechanical", "Security / IT / DevOps", "Legal & Compliance", "Other"]
CITIES = ["Bengaluru", "Mumbai", "Pune", "Hyderabad", "Delhi NCR", "Chennai", "Kolkata", "Ahmedabad",
          "Remote (India)", "Other India", "Not India"]
TYPES = ["Internship", "Full-time (fresher / 0-1 yr)", "Full-time (1-2 yrs)", "Not entry-level"]

SYSTEM = f"""You tag job posts for a career platform for Indian college students and freshers.
For EACH post return one JSON object. Use ONLY these values.

role: one of {ROLES}
  - Judge by the work done, not the department name. "Software Development Engineer" -> Software Engineering;
    "Machine Learning / GenAI / Research Engineer" -> AI / ML; "Data Analyst / BI / Data Engineer" -> Data & Analytics;
    DevOps, SRE, InfoSec -> Security / IT / DevOps.
city: one of {CITIES}
  - Gurgaon/Gurugram, Noida, Delhi, Faridabad, Ghaziabad -> "Delhi NCR". Navi Mumbai/Thane -> "Mumbai".
  - If several Indian cities are listed use the FIRST one. Fully remote within India -> "Remote (India)".
  - A city outside India only -> "Not India".
job_type: one of {TYPES}
  - "Internship" for interns/trainees/apprentices. "Full-time (fresher / 0-1 yr)" if the post says fresher, new grad,
    0-1 years, or asks for no experience. "Full-time (1-2 yrs)" if the minimum experience is 1-2 years.
    "Not entry-level" if the minimum required experience is 3+ years, or senior/lead/manager level.
  - Use the stated MINIMUM experience, not the preferred. If nothing states experience, decide from the title/duties.
fresher_ok: true only if job_type is not "Not entry-level".
min_years: minimum years of experience required as a number (0 for interns/freshers), or null if unstated.
confidence: 0-1, your confidence in role+city+job_type together.

Return ONLY a JSON array, same order and same "id" values as the input, no prose, no markdown fences.
Each element: {{"id": str, "role": str, "city": str, "job_type": str, "fresher_ok": bool, "min_years": number|null, "confidence": number}}"""


def _chat_openrouter(user):
    import urllib.request
    body = {"model": MODEL, "max_tokens": 2000, "reasoning": {"enabled": False}, "usage": {"include": True},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                  "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.load(r)
    u = d.get("usage") or {}
    return d["choices"][0]["message"]["content"], u.get("prompt_tokens", 0), u.get("completion_tokens", 0), u.get("cost")


def _chat_anthropic(client, user):
    r = client.messages.create(model=MODEL, max_tokens=2000, system=SYSTEM, thinking={"type": "disabled"},
                               messages=[{"role": "user", "content": user}])
    return r.content[0].text, r.usage.input_tokens, r.usage.output_tokens, None


def content_hash(p):
    return hashlib.sha1(f"{p['title']}|{p['location_raw']}|{p['description'][:1500]}".encode()).hexdigest()[:16]


def _render(batch):
    return "\n\n".join(
        f"### id={p['_h']}\ntitle: {p['title']}\ncompany: {p['company']}\nlocation: {p['location_raw']}\n"
        f"description: {p['description'][:1500]}" for p in batch)


def _parse(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\[.*\]", text, re.S)
    return json.loads(m.group(0) if m else text)


def _valid(t):
    return (t.get("role") in ROLES and t.get("city") in CITIES and t.get("job_type") in TYPES
            and isinstance(t.get("fresher_ok"), bool))


def tag_posts(posts, cache_path="data/tags_cache.json", usage_path="data/usage.jsonl", log=print):
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    for p in posts:
        p["_h"] = content_hash(p)
    todo = [p for p in posts if p["_h"] not in cache]
    log(f"tagger: {len(posts)} posts, {len(posts) - len(todo)} cached, {len(todo)} to tag with {MODEL}")
    if todo and not (USE_OR or os.environ.get("ANTHROPIC_API_KEY")):
        from . import rules
        log("tagger: no ANTHROPIC_API_KEY -> using rule-based fallback tagger (lower accuracy, $0)")
        for p in todo:
            cache[p["_h"]] = rules.tag(p)
        todo = []
    if todo:
        client = None
        if not USE_OR:
            import anthropic
            client = anthropic.Anthropic()
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            for attempt in range(3):
                try:
                    text, tin, tout, cost = (_chat_openrouter(_render(batch)) if USE_OR
                                             else _chat_anthropic(client, _render(batch)))
                    out = {t["id"]: t for t in _parse(text)}
                    with open(usage_path, "a") as f:
                        f.write(json.dumps({"ts": time.time(), "model": MODEL, "posts": len(batch),
                                            "in": tin, "out": tout, "cost": cost}) + "\n")
                    bad = 0
                    for p in batch:
                        t = out.get(p["_h"])
                        if t and _valid(t):
                            cache[p["_h"]] = t
                        else:
                            bad += 1
                    if bad:
                        log(f"  batch {i // BATCH}: {bad} invalid/missing -> retried next run")
                    break
                except Exception as e:                      # rate limit, bad JSON, network
                    log(f"  batch {i // BATCH} attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:120]}")
                    time.sleep(2 ** attempt)
            json.dump(cache, open(cache_path, "w"))
    for p in posts:
        t = cache.get(p["_h"])
        p["tags"] = t
    return posts


def cost_summary(usage_path="data/usage.jsonl"):
    if not os.path.exists(usage_path):
        return None
    rows = [json.loads(l) for l in open(usage_path)]
    n, tin, tout = sum(r["posts"] for r in rows), sum(r["in"] for r in rows), sum(r["out"] for r in rows)
    usd = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
    if all(r.get("cost") is not None for r in rows):
        usd = sum(r["cost"] for r in rows)          # OpenRouter-reported actual spend
    return {"posts": n, "input_tokens": tin, "output_tokens": tout, "usd": round(usd, 4),
            "usd_per_1000_posts": round(usd / n * 1000, 4) if n else None}
