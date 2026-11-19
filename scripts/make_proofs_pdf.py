import csv, io, json
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak

jobs_file = json.load(open("data/jobs.json"))
jobs, meta = jobs_file["jobs"], jobs_file["meta"]
stats = json.load(open("data/board_stats.json"))
dd = json.load(open("data/dedupe_log.json"))
rows = list(csv.DictReader(open("data/eval_sheet.csv")))

total = sum(v["total"] for v in stats.values())
india = sum(v["india"] for v in stats.values())
cand = sum(v["fresher_candidates"] for v in stats.values())
funnel = [("All posts\n(63 boards)", total), ("In India", india), ("Entry level\ncandidates", cand),
          ("After dedupe", meta["after_dedupe"]), ("Published", meta["count"])]

def fig_png(fn, w=15, h=6):
    fig, ax = plt.subplots(figsize=(w / 2.54, h / 2.54), dpi=200)
    fn(ax)
    fig.tight_layout()
    b = io.BytesIO(); fig.savefig(b, format="png"); plt.close(fig); b.seek(0)
    return Image(b, width=w * cm, height=h * cm)

def bars(ax, labels, vals, horizontal=False, color="#2b4c7e"):
    if horizontal:
        ax.barh(labels[::-1], vals[::-1], color=color)
        for i, v in enumerate(vals[::-1]): ax.text(v, i, f" {v}", va="center", fontsize=7)
    else:
        ax.bar(labels, vals, color=color)
        for i, v in enumerate(vals): ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=7)
    ax.tick_params(labelsize=7)
    for s in ("top", "right"): ax.spines[s].set_visible(False)

comp = Counter(j["company"] for j in jobs).most_common()
role = Counter(j["role"] for j in jobs).most_common()
jtype = Counter(j["job_type"] for j in jobs)
conf_low = sum(1 for j in jobs if (j.get("confidence") or 1) < 0.7)
top3 = sum(c for _, c in comp[:3])

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=16, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, keepWithNext=1)
B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=9, leading=12.5)
S = ParagraphStyle("S", parent=B, fontSize=7.5, textColor=colors.HexColor("#555555"))

def table(data, widths=None, fs=7.5):
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), fs), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf4")),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t

def P(t, st=B): return Paragraph(t, st)

e = []
e += [P("Proofs: Fresher Jobs India pipeline", H1),
      P(f"Data from the run on {meta['updated_at'][:10]}. Repo: github.com/Rohit-girish-Belagali/beep-fresher-jobs. "
        "Live: https://jobs.rohitgb.info. Every number below is computed from files in the repo "
        "(data/jobs.json, data/board_stats.json, data/dedupe_log.json, data/eval_sheet.csv, data/usage.jsonl) "
        "by scripts/make_proofs_pdf.py.", B)]

e += [P("1. Only about 2 in 100 posts are useful for a fresher", H2),
      fig_png(lambda ax: bars(ax, [a for a, _ in funnel], [b for _, b in funnel])),
      P(f"{total:,} posts pulled, {india:,} in India, {cand} entry level candidates, {meta['after_dedupe']} after dedupe, "
        f"{meta['count']} published. Yield: {meta['count'] / total:.1%}. The count changes daily (225 the day before), "
        "so the 200+ target needs a wide net. Source: data/board_stats.json and the meta block of data/jobs.json.", B)]

e += [P("2. A few companies fill most of the list", H2),
      fig_png(lambda ax: bars(ax, [c for c, _ in comp[:10]], [n for _, n in comp[:10]], True), h=6.5),
      P(f"Top 3 companies ({', '.join(c for c, _ in comp[:3])}) = {top3} of {len(jobs)} posts = {top3 / len(jobs):.0%}.", B),
      fig_png(lambda ax: bars(ax, [r for r, _ in role], [n for _, n in role], True, "#7e4c2b"), h=8),
      P("Roles with 1 post: " + ", ".join(r for r, n in role if n == 1) + ". "
        "apna reposts the same job per city (Field Sales in Vadodara, Pune, Surat, Gandhinagar, Lucknow), "
        "so the fuzzy dedupe, which compares inside one city bucket, keeps them as separate rows.", B)]

e += [P("3. Many fresher jobs are not really fresher", H2)]
td = [["Job type", "Posts", "Share"]] + [[k, v, f"{v / len(jobs):.0%}"] for k, v in jtype.most_common()]
e += [table(td, [8 * cm, 2.5 * cm, 2.5 * cm], 8), Spacer(1, 4),
      P(f"{conf_low} posts ({conf_low / len(jobs):.0%}) have model confidence under 0.7. Source: job_type and confidence fields in data/jobs.json.", B)]

wrong = [r for r in rows if "0" in (r["role_ok"], r["city_ok"], r["type_ok"])]
td = [["#", "Post", "Tag problem"]]
for r in wrong:
    td.append([rows.index(r) + 1, Paragraph(f"{r['title'][:60]} ({r['company']})", S), Paragraph(r["notes"].replace("Claude review: ", ""), S)])
e += [P("Posts where a tag was wrong (from the 50-post sample)", H2), table(td, [1 * cm, 7.5 * cm, 8.5 * cm])]

def acc(col):
    v = [int(r[col]) for r in rows if r[col] in ("0", "1")]
    return sum(v), len(v)
cost = meta["cost"]
e += [P("4. Tagging accuracy and cost", H2),
      table([["Metric", "Correct / judged", "Accuracy"]] + [[n, f"{acc(c)[0]} / {acc(c)[1]}", f"{acc(c)[0] / acc(c)[1]:.0%}"]
            for n, c in (("Role", "role_ok"), ("City", "city_ok"), ("Job type", "type_ok"))], [6 * cm, 4 * cm, 3 * cm], 8),
      Spacer(1, 4),
      P("Method, stated plainly: the verdicts were made by Claude reading each post's title, location and full live description. "
        "They were not made by hand by the author. One post (title too vague) was excluded. Job type was judged only where the post "
        "states an experience requirement, so its sample is smaller. Per-row verdicts and reasons: data/eval_sheet.csv.", B),
      P(f"Cost: {cost['posts']} posts tagged, {cost['input_tokens']:,} input tokens, {cost['output_tokens']:,} output tokens, "
        f"${cost['usd']} total = ${cost['usd_per_1000_posts']} per 1,000 posts (OpenRouter reported spend, Claude Haiku 5.5). Source: data/usage.jsonl.", B)]

reasons = Counter(d["reason"] for d in dd)
e += [P("5. Dedupe", H2),
      P(f"{meta['fetched']} candidates in, {meta['after_dedupe']} out, {len(dd)} dropped (" +
        ", ".join(f"{k}: {v}" for k, v in reasons.items()) + "). Source: data/dedupe_log.json.", B),
      P("6. Reproduce", H2),
      P("python3 -m jobpipe.pipeline, then PYTHONPATH=. python3 scripts/score_eval.py, then python3 scripts/make_proofs_pdf.py. "
        "The daily GitHub Action (06:00 IST) re-runs the pipeline and redeploys the site.", B)]

SimpleDocTemplate("docs/proofs.pdf", pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                  bottomMargin=1.8 * cm, title="Proofs: Fresher Jobs India pipeline").build(e)
print("wrote docs/proofs.pdf")
