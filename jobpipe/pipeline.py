import concurrent.futures as cf
import datetime as dt
import json
import os
import sys

from . import sources as S
from .config import BOARDS
from .dedupe import dedupe
from .tagger import tag_posts, cost_summary

DATA = "data"


def fetch_all(log=print):
    def run(b):
        kind, slug, label = b
        try:
            return b, list(S.FETCHERS[kind](slug, label))
        except Exception as e:
            log(f"  ! {kind}/{slug} failed: {type(e).__name__}: {e}")
            return b, []
    posts, stats = [], {}
    with cf.ThreadPoolExecutor(12) as ex:
        for (kind, slug, label), ps in ex.map(run, BOARDS):
            india = [p for p in ps if S.is_india(p)]
            cand = [p for p in india if S.llm_candidate(p)]
            stats[f"{kind}/{slug}"] = {"total": len(ps), "india": len(india), "fresher_candidates": len(cand)}
            posts += cand
    return posts, stats


def main():
    os.makedirs(DATA, exist_ok=True)
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    raw, stats = fetch_all()
    print(f"fetched: {len(raw)} fresher-candidate India posts from {len(BOARDS)} boards")
    uniq, dropped = dedupe(raw)
    print(f"dedupe: {len(raw)} -> {len(uniq)} ({len(dropped)} duplicates dropped)")
    tagged = tag_posts(uniq)
    prev = {}
    if os.path.exists(f"{DATA}/jobs.json"):
        prev = {j["id"]: j for j in json.load(open(f"{DATA}/jobs.json"))["jobs"]}
    jobs = []
    for p in tagged:
        t = p.get("tags")
        if not t or not t["fresher_ok"] or t["city"] == "Not India":
            continue
        jid = p["_h"]
        jobs.append({"id": jid, "title": p["title"], "company": p["company"], "location": p["location_raw"],
                     "url": p["url"], "source": p["source"], "role": t["role"], "city": t["city"],
                     "job_type": t["job_type"], "min_years": t.get("min_years"), "confidence": t.get("confidence"),
                     "posted_at": p.get("posted_at"), "first_seen": prev.get(jid, {}).get("first_seen", now),
                     "snippet": p["description"][:280]})
    jobs.sort(key=lambda j: j["first_seen"], reverse=True)
    meta = {"updated_at": now, "count": len(jobs), "fetched": len(raw), "after_dedupe": len(uniq),
            "boards": len(BOARDS), "cost": cost_summary()}
    json.dump({"meta": meta, "jobs": jobs}, open(f"{DATA}/jobs.json", "w"), indent=1)
    json.dump(stats, open(f"{DATA}/board_stats.json", "w"), indent=1)
    json.dump([{"id": a, "reason": b} for a, b in dropped], open(f"{DATA}/dedupe_log.json", "w"))
    os.makedirs("site", exist_ok=True)
    json.dump({"meta": meta, "jobs": jobs}, open("site/jobs.json", "w"))
    print(f"published {len(jobs)} jobs  cost={meta['cost']}")


if __name__ == "__main__":
    main()
