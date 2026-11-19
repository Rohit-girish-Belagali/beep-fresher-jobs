"""Render docs/submission.md to site/doc/index.html and copy its proof files next to it."""
import shutil, subprocess, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "site" / "doc"
out.mkdir(parents=True, exist_ok=True)
for src in ["docs/jobs_data.csv", "docs/proofs.pdf", "data/eval_sheet.csv", "data/eval_review.md",
            "data/board_stats.json", "data/dedupe_log.json", "data/usage.jsonl"]:
    shutil.copy(root / src, out / pathlib.Path(src).name)
css = """<style>body{font:16px/1.6 -apple-system,Segoe UI,sans-serif;max-width:860px;margin:32px auto;padding:0 20px;color:#1a1a1a}
pre{background:#f4f4f1;padding:12px;overflow:auto;border-radius:8px;font-size:13px}code{background:#f4f4f1;padding:1px 4px;border-radius:4px}
h1,h2{border-bottom:1px solid #e5e5e0;padding-bottom:6px}.files{background:#f8f8f5;border:1px solid #e5e5e0;border-radius:8px;padding:10px 16px}</style>"""
files = ("<div class='files'><b>Files:</b> <a href='../'>live job site</a> · <a href='jobs_data.csv'>jobs_data.csv</a> · "
         "<a href='eval_sheet.csv'>eval_sheet.csv</a> · <a href='proofs.pdf'>proofs.pdf</a> · <a href='board_stats.json'>board_stats.json</a> · "
         "<a href='dedupe_log.json'>dedupe_log.json</a> · <a href='usage.jsonl'>usage.jsonl</a> · "
         "<a href='https://github.com/Rohit-girish-Belagali/beep-fresher-jobs'>repo</a></div>")
(out / "head.html").write_text(css)
(out / "before.html").write_text(files)
subprocess.run(["pandoc", str(root / "docs/submission.md"), "-f", "gfm", "-s", "--metadata", "title=Fresher jobs India: working doc",
                "-H", str(out / "head.html"), "-B", str(out / "before.html"), "-o", str(out / "index.html")], check=True)
(out / "head.html").unlink(); (out / "before.html").unlink()
print("built", out / "index.html")
