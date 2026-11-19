"""Fetchers for public, documented job-board APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workable).

These endpoints are published by the ATS vendors specifically so that companies' own
job listings can be consumed by third parties - no HTML scraping, no login walls,
no robots.txt / ToS conflicts. Every post links back to the employer's own apply page.
"""
import html
import json
import re
import urllib.request
import urllib.error

UA = "BeepFresherJobsBot/1.0 (student project; polite, 1 req per board per run)"

INDIA_RE = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|navi mumbai|pune|hyderabad|delhi|new delhi|gurgaon|gurugram|noida|"
    r"greater noida|chennai|kolkata|ahmedabad|jaipur|kochi|cochin|trivandrum|thiruvananthapuram|indore|"
    r"chandigarh|mohali|coimbatore|lucknow|bhubaneswar|nagpur|vadodara|surat|mysuru|mysore)\b", re.I)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def strip_html(s):
    s = html.unescape(s or "")           # greenhouse double-escapes
    s = re.sub(r"<(br|/p|/li|/h\d|/div)\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def _post(source, company, jid, title, location, url, desc, posted=None):
    return {
        "source": source, "company": company, "source_id": f"{source}:{company}:{jid}",
        "title": (title or "").strip(), "location_raw": (location or "").strip(),
        "url": url, "description": strip_html(desc)[:6000], "posted_at": posted,
    }


def greenhouse(slug, label=None):
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    for j in (d or {}).get("jobs", []):
        yield _post("greenhouse", label or slug, j["id"], j["title"], (j.get("location") or {}).get("name"),
                    j["absolute_url"], j.get("content"), (j.get("first_published") or j.get("updated_at")))


def lever(slug, label=None):
    d = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    for j in d if isinstance(d, list) else []:
        c = j.get("categories") or {}
        loc = c.get("location") or ""
        if c.get("allLocations"):
            loc = "; ".join(c["allLocations"])
        desc = j.get("descriptionPlain") or j.get("description") or ""
        for l in j.get("lists") or []:
            desc += "\n" + (l.get("text") or "") + "\n" + (l.get("content") or "")
        yield _post("lever", label or slug, j["id"], j["text"], loc, j["hostedUrl"], desc,
                    j.get("createdAt") and __import__("datetime").datetime.utcfromtimestamp(j["createdAt"] / 1000).isoformat())


def ashby(slug, label=None):
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    for j in (d or {}).get("jobs", []):
        if not j.get("isListed", True):
            continue
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        yield _post("ashby", label or slug, j["id"], j["title"], "; ".join(x for x in locs if x),
                    j.get("jobUrl"), j.get("descriptionPlain") or j.get("descriptionHtml"), j.get("publishedAt"))


def smartrecruiters(slug, label=None):
    off = 0
    while off < 600:
        d = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={off}&country=in")
        items = (d or {}).get("content") or []
        for j in items:
            loc = j.get("location") or {}
            desc = ""
            if not re.search(r"\b(senior|sr\.?|staff|principal|lead|director|head|manager)\b", j["name"], re.I):
                det = _get(j["ref"]) or {}   # detail call only for non-senior titles (keeps runs fast + polite)
                sec = (det.get("jobAd") or {}).get("sections") or {}
                desc = " ".join((v or {}).get("text", "") for v in sec.values())
            yield _post("smartrecruiters", label or slug, j["id"], j["name"],
                        ", ".join(x for x in [loc.get("city"), loc.get("country", "").upper()] if x),
                        f"https://jobs.smartrecruiters.com/{slug}/{j['id']}", desc, j.get("releasedDate"))
        if len(items) < 100:
            break
        off += 100


def workable(slug, label=None):
    d = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    for j in (d or {}).get("jobs", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        yield _post("workable", label or slug, j.get("shortcode"), j["title"], loc, j.get("url"),
                    j.get("description"), j.get("published_on"))


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby,
            "smartrecruiters": smartrecruiters, "workable": workable}


def is_india(p):
    return bool(INDIA_RE.search(p["location_raw"]))


# --- cheap pre-filter: is this plausibly a fresher / intern / 0-2 yr role? (LLM makes the final call) ---
SENIOR_RE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|head|director|manager|vp|architect|distinguished|"
                       r"sde[- ]?(iii|3)|sde[- ]?iv|\biii\b|\biv\b|l[5-9])\b", re.I)
TITLE_ENTRY_RE = re.compile(r"\b(intern(ship)?s?|fresher|trainee|graduate|new grad|campus|apprentice|early career|"
                            r"junior|jr\.?|associate|entry[- ]level|sde[- ]?(1|i)\b|engineer i\b|analyst i\b|"
                            r"software engineer 1|engineer 1)\b", re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+|-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)", re.I)
DESC_ENTRY_RE = re.compile(r"\b(freshers?|recent graduates?|fresh graduates?|0\s*(?:-|–|to)\s*[12]\s*(?:years?|yrs?)|"
                           r"no (?:prior )?experience|entry[- ]level|new grad|batch of 20\d\d|graduating in 20\d\d|"
                           r"final[- ]year|pursuing (?:a |your )?(?:bachelor|b\.?tech|degree|master))", re.I)


def min_years(text):
    ys = [int(m.group(1)) for m in YEARS_RE.finditer(text[:4000]) if int(m.group(1)) <= 20]
    return min(ys) if ys else None


def fresher_candidate(p):
    t = p["title"]
    if TITLE_ENTRY_RE.search(t) and not re.search(r"\b(senior|sr\.?|staff|principal|lead|director|head)\b", t, re.I):
        return True
    if SENIOR_RE.search(t):
        return False
    if DESC_ENTRY_RE.search(p["description"]):
        return True
    return False


def llm_candidate(p):
    """Wide, cheap pre-filter: drop only obviously senior titles or posts whose text asks for 3+ years.
    The LLM then decides fresher-suitability (so 'Software Engineer' posts that welcome 0-2 yrs are kept)."""
    if fresher_candidate(p):
        return True
    if SENIOR_RE.search(p["title"]):
        return False
    y = min_years(p["description"])
    return y is None or y <= 2
