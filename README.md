# Fresher Jobs India

Collects fresher / internship posts in India from public ATS job-board APIs, de-duplicates, tags each post
(role, city, job type) and publishes a searchable static page that refreshes daily.

```
fetch (Greenhouse/Lever/Ashby/SmartRecruiters/Workable public APIs, 55 boards)
  -> India filter -> cheap pre-filter (drop senior / 3+ yrs)
  -> dedupe (exact URL/key + fuzzy title&description)
  -> tag (Claude Haiku 5.5, cached by content hash; rule-based fallback if no API key)
  -> data/jobs.json + site/jobs.json -> static site/index.html
GitHub Action (daily 06:00 IST) re-runs and redeploys to GitHub Pages.
```

Run: `pip install -r requirements.txt && ANTHROPIC_API_KEY=... python -m jobpipe.pipeline` then serve `site/`.
Add a company: one line in `jobpipe/config.py`.

## Why public ATS APIs
They are published for third-party consumption, so no HTML scraping or ToS conflict; every post links to the employer's own apply page.
Job portals that forbid scraping (Naukri, Internshala, LinkedIn) are deliberately not used.

## Accuracy and cost
Fill `data/eval_sheet.csv` (50 seeded-random posts, `python scripts/make_eval_sheet.py`) and run `python scripts/score_eval.py`.
Cost per 1,000 posts is computed from logged token usage in `data/usage.jsonl` (`cost_summary`).
Tagged with Claude Haiku 5.5 via OpenRouter (`OPENROUTER_API_KEY`); measured cost ~$0.11 per 1,000 posts. Accuracy on a 50-post sample (Claude-reviewed, not human hand-checked): role 94%, city 94%, job type 73% (where experience is stated). See `docs/submission.md`.
