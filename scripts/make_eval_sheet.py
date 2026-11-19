"""Sample 50 published posts (seeded, so reproducible) into a CSV for hand-checking.
Fill the *_ok columns with 1/0 (or correct value), then run scripts/score_eval.py."""
import csv, json, random
jobs = json.load(open("data/jobs.json"))["jobs"]
random.Random(42).shuffle(jobs)
with open("data/eval_sheet.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "title", "company", "location", "url", "tag_role", "tag_city", "tag_job_type",
                "role_ok", "city_ok", "type_ok", "correct_role", "correct_city", "correct_type", "notes"])
    for j in jobs[:50]:
        w.writerow([j["id"], j["title"], j["company"], j["location"], j["url"], j["role"], j["city"], j["job_type"]])
print("wrote data/eval_sheet.csv (50 rows)")
