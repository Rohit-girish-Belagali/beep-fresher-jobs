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

## 6. Key design decisions I made

Claude Code (Sonnet 5.5) wrote the code under my direction, as noted in section 2. The design choices below are mine.

**Don't scrape. Use official ATS APIs.**
My first instinct was to hit Naukri/Internshala/LinkedIn. I ruled that out: ToS risk, bot detection, and brittle HTML parsers. Every major tech company posts on a public ATS (Greenhouse, Lever, Ashby, SmartRecruiters, Workable) that returns structured JSON. I hand-picked the 55 boards in `jobpipe/config.py` — a mix of India-headquartered companies (Paytm, Meesho, CRED, Groww, InMobi, Glance, Sarvam AI, apna) and global tech firms with India engineering centres (Stripe, MongoDB, Databricks, Okta, Bosch, Freshworks, ServiceNow). That list is my editorial call, not an algorithm.

**Two-stage dedupe with a fuzzy threshold I tuned.**
An exact URL hash misses the same job listed under multiple req IDs. I added fuzzy matching on title (≥0.90) + description prefix (≥0.85), bucketed by company + city. I landed on those thresholds by looking at the actual dropped pairs in `data/dedupe_log.json` — 0.80 ate legitimate different roles at the same company, 0.95 let obvious re-posts through. The final numbers are from that manual inspection.

**Pre-filter to control LLM cost, not to decide entry-level.**
Dropping posts with senior titles or ≥3 yrs in the description before the LLM run is cheap (regex). But "junior/fresher" language is unreliable across companies — Bosch writes "0-2 years preferred" in a paragraph, Meesho says nothing. So the pre-filter passes borderline posts to the LLM rather than dropping them. That was a deliberate choice to maximise recall and shift the precision trade-off to tagging.

**Haiku-class model, batch of 8, hash cache.**
The cost target was <$0.20 per 1,000 posts. Opus/Sonnet would over-qualify the task (structured output from a fixed schema). Haiku 5.5 at $0.10/$0.50 per 1M tokens hits ~$0.11/1k. I settled on a batch of 8 after testing: smaller batches waste per-request overhead, larger ones occasionally hit the 2000-token output cap and lose posts. The content-hash cache (`data/tags_cache.json`) means re-runs after a code change cost nothing for already-tagged posts.

**Taxonomy I defined.**
16 role buckets, 11 city buckets, 4 job-type buckets — I wrote the full taxonomy and the city-mapping rules (Gurgaon/Noida/Faridabad → Delhi NCR; Navi Mumbai/Thane → Mumbai; "Remote India" vs. city-agnostic global remote). The LLM's task is to apply my taxonomy, not invent its own.
