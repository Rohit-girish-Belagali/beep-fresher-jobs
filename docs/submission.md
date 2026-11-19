# Submission working doc

## 1. Data
- `docs/jobs_data.csv`: all 225 published posts (title, company, city, role, job type, source, apply URL).
- `data/eval_sheet.csv`: 50 seeded-random posts for the hand-check (verdicts filled; see section 4).
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
- Tagging accuracy on the 50-post sample (49 judged; 1 excluded because its title was too vague): role 46/49 = 94%, city 46/49 = 94%, job type 19/26 = 73%.
  - Job type was judged only where the live post states an experience requirement (26 of 49). The other 23 are not counted, so the 73% figure rests on a smaller sample.
  - **Method, stated plainly:** these verdicts were made by Claude reading each post's title, location and full description, not by me by hand. I have not independently re-checked them. Per-row verdicts and reasons are in `data/eval_sheet.csv`.
  - Main errors found: Noida/Bangalore posts tagged "Other India" (3), roles requiring 2-6 yrs tagged "fresher / 0-1 yr" (5), one post requiring 4+ yrs tagged 1-2 yrs, one MiL/SiL software-testing role tagged Hardware.
- Cost per 1,000 posts: ~$0.111 (OpenRouter-reported spend, 416 posts; data/usage.jsonl)

## 5. What broke and how it was fixed
- Strict title/experience filter gave only ~116 candidates -> widened pre-filter, let the LLM decide.
- SmartRecruiters detail calls were slow -> fetch detail only for non-senior titles.
- Greenhouse descriptions are double-escaped HTML -> unescape twice before stripping.
- Same job listed per location/requisition -> added fuzzy dedupe. Latest run: 114 duplicates dropped (109 exact, 5 fuzzy), see data/dedupe_log.json.

## 6. Key design decisions I made

**AI usage summary:** Claude Code (Sonnet 5.5) wrote the implementation code — the fetchers, deduper, tagger, pipeline, and the site HTML. Claude Haiku 5.5 runs the production tagging. I used both as tools, the same way I would use a compiler or a library. The parts below are what I decided, iterated on, and would defend in a live call: the architecture, the data sources, the taxonomy, and the trade-offs.

The design choices below are mine.

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

## 7. Research: 3 things I found

All numbers come from the pipeline output of the 2026-11-19 run (`data/jobs.json` meta, `data/board_stats.json`, `data/dedupe_log.json`). To check them: run `python3 -m jobpipe.pipeline` and read those files.

**1. Only 2 out of 100 job posts are useful for a fresher.**
I pulled 10,410 posts from 63 company boards. 2,403 are in India. 511 look entry level after my pre-filter. 397 are left after dedupe, and 210 are published after the LLM tagging. So the yield is 2.0%.
Proof: `data/board_stats.json` (total 10,410 / india 2,403 / candidates 511), `data/jobs.json` meta (after_dedupe 397, count 210).
Why it matters: "200+ fresher jobs" needs a very wide net. A few boards will never give 200. Also the count moves every day: it was 225 one day before and 210 now, so the number is close to the limit, not safe.

**2. Three companies are more than half of the list, and two roles are almost nothing.**
apna 65, Paytm 31, Bosch 21. That is 117 of 210, so 56%. Without apna only 145 posts are left. Sales (52) and Customer Support (38) are 43% of everything. AI / ML has 1 post and Design / UX has 1 post.
Proof: company and role counts from `data/jobs.json` (`Counter` on the `company` and `role` fields). Raw per-board numbers in `data/board_stats.json`: Bosch gave 110 candidates and apna 109 out of 511.
Why it matters: a fresher who wants an AI or design job finds almost nothing, even if the list looks big. Also apna posts the same job again for every city (Field Sales in Vadodara, Pune, Surat, Gandhinagar, Lucknow), so the fuzzy dedupe only works inside one city bucket and these stay as separate rows. For a product I would show the company mix on the page and not hide it.

**3. Many "fresher" jobs are not really fresher, and the tags are not equally sure.**
Of the 210 posts, 109 (52%) are fresher / 0-1 yr, 15 (7%) are internships, and 86 (41%) ask for 1-2 years. 53 posts (25%) have model confidence under 0.7.
Proof: `job_type` and `confidence` fields in `data/jobs.json`. Example of a bad source field: post 45 in `data/eval_review.md` has "Navi Mumbai" in the title but "Bengaluru, Karnataka" in the location field.
Why it matters: if I filtered only by title words ("fresher", "intern") I would miss or mislabel almost half. And the location field from the company can be wrong, so city tags must read the title and the text too, not only the field. The 53 low-confidence posts are the first ones to hand-check.
