"""Two-stage de-duplication.

1. exact: same canonical URL, or same (company, normalised title, normalised location)
2. fuzzy: within a (company, city) bucket, titles with difflib ratio >= 0.9 AND near-identical
   description prefix are the same job re-posted (common with ATS 'repost' + multi-req hiring).
"""
import difflib
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

NOISE = re.compile(r"\b(m/f|f/m|all genders|hybrid|remote|immediate joiner|urgent|hiring|opening|2025|2026|batch)\b", re.I)


def norm_title(t):
    t = NOISE.sub(" ", t.lower())
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.sub(r"[^a-z0-9+# ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def canon_url(u):
    s = urlsplit(u or "")
    return urlunsplit((s.scheme, s.netloc.lower(), s.path.rstrip("/"), "", ""))


def key(p):
    return hashlib.sha1(f"{p['company'].lower()}|{norm_title(p['title'])}|{(p.get('city') or p['location_raw']).lower()}".encode()).hexdigest()[:16]


def dedupe(posts):
    """Return (unique_posts, dropped) ; keeps the earliest-listed copy and records merged urls."""
    seen_url, seen_key, kept, dropped = {}, {}, [], []
    buckets = {}
    for p in posts:
        u, k = canon_url(p["url"]), key(p)
        if u in seen_url or k in seen_key:
            dropped.append((p["source_id"], "exact")); continue
        b = buckets.setdefault((p["company"].lower(), p["location_raw"].lower()), [])
        dup = None
        for q in b:
            if difflib.SequenceMatcher(None, norm_title(p["title"]), norm_title(q["title"])).ratio() >= 0.9 and \
               difflib.SequenceMatcher(None, p["description"][:400], q["description"][:400]).ratio() >= 0.85:
                dup = q; break
        if dup:
            dropped.append((p["source_id"], "fuzzy")); continue
        seen_url[u] = seen_key[k] = True
        b.append(p); kept.append(p)
    return kept, dropped
