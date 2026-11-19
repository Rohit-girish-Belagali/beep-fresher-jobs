import csv, json, os
rows = list(csv.DictReader(open("data/eval_sheet.csv")))
done = [r for r in rows if r["role_ok"] in ("0", "1")]
print(f"{len(done)}/{len(rows)} rows checked")
for k in ("role", "city", "type"):
    v = [int(r[k + "_ok"]) for r in done if r[k + "_ok"] in ("0", "1")]
    print(f"{k:5s} accuracy: {sum(v)}/{len(v)} = {sum(v)/max(len(v),1):.0%}")
allok = [all(r[k + "_ok"] == "1" for k in ("role", "city", "type")) for r in done]
print(f"all three correct: {sum(allok)}/{len(allok)}")
if os.path.exists("data/usage.jsonl"):
    from jobpipe.tagger import cost_summary
    print("cost:", cost_summary())
