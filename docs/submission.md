# Submission working doc

## 1. Data
- `docs/jobs_data.csv`: all 225 published posts (title, company, city, role, job type, source, apply URL).
- `data/eval_sheet.csv`: 50 seeded-random posts for the hand-check (verdict columns still blank).
- Sources: public ATS APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workable), 55 company boards. No scraping of job portals.

## 2. AI tools used
- Claude Code (Claude Sonnet 5.5): wrote the pipeline code, under my direction.
- Claude Haiku 5.5 (`claude-haiku-5-5`): production tagger. Run via OpenRouter (`anthropic/claude-haiku-5.5`).
- Rule-based fallback tagger (`jobpipe/rules.py`): used only when no API key is set.

## 3. Prompts
### Tagging prompt (system prompt, `jobpipe/tagger.py`)
```
You tag job posts for a career platform for Indian college students and freshers.
For EACH post return one JSON object. Use ONLY these values.

role: one of ['Software Engineering', 'Data & Analytics', 'AI / ML', 'Product Management', 'Design / UX', 'Marketing & Growth', 'Sales & Business Development', 'Operations & Supply Chain', 'Finance & Accounting', 'HR & Recruiting', 'Customer Support / Success', 'Content & Writing', 'Hardware / Electrical / Mechanical', 'Security / IT / DevOps', 'Legal & Compliance', 'Other']
  - Judge by the work done, not the department name. "Software Development Engineer" -> Software Engineering;
    "Machine Learning / GenAI / Research Engineer" -> AI / ML; "Data Analyst / BI / Data Engineer" -> Data & Analytics;
    DevOps, SRE, InfoSec -> Security / IT / DevOps.
city: one of ['Bengaluru', 'Mumbai', 'Pune', 'Hyderabad', 'Delhi NCR', 'Chennai', 'Kolkata', 'Ahmedabad', 'Remote (India)', 'Other India', 'Not India']
  - Gurgaon/Gurugram, Noida, Delhi, Faridabad, Ghaziabad -> "Delhi NCR". Navi Mumbai/Thane -> "Mumbai".
  - If several Indian cities are listed use the FIRST one. Fully remote within India -> "Remote (India)".
  - A city outside India only -> "Not India".
job_type: one of ['Internship', 'Full-time (fresher / 0-1 yr)', 'Full-time (1-2 yrs)', 'Not entry-level']
  - "Internship" for interns/trainees/apprentices. "Full-time (fresher / 0-1 yr)" if the post says fresher, new grad,
    0-1 years, or asks for no experience. "Full-time (1-2 yrs)" if the minimum experience is 1-2 years.
    "Not entry-level" if the minimum required experience is 3+ years, or senior/lead/manager level.
  - Use the stated MINIMUM experience, not the preferred. If nothing states experience, decide from the title/duties.
fresher_ok: true only if job_type is not "Not entry-level".
min_years: minimum years of experience required as a number (0 for interns/freshers), or null if unstated.
confidence: 0-1, your confidence in role+city+job_type together.

Return ONLY a JSON array, same order and same "id" values as the input, no prose, no markdown fences.
Each element: {"id": str, "role": str, "city": str, "job_type": str, "fresher_ok": bool, "min_years": number|null, "confidence": number}
```
Each user message holds 8 posts rendered as `### id=... / title / company / location / description[:1500]`.

## 4. Numbers (to fill after the LLM run)
- Tagging accuracy on 50 hand-checked posts: TODO
- Cost per 1,000 posts: ~$0.111 (OpenRouter-reported spend, 416 posts; data/usage.jsonl)

## 5. What broke and how it was fixed
- Strict title/experience filter gave only ~116 candidates -> widened pre-filter, let the LLM decide.
- SmartRecruiters detail calls were slow -> fetch detail only for non-senior titles.
- Greenhouse descriptions are double-escaped HTML -> unescape twice before stripping.
- Same job listed per location/requisition -> fuzzy dedupe (84-110 dropped).
