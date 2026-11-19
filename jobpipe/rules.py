"""Rule-based fallback tagger (no LLM). Used when ANTHROPIC_API_KEY is absent; same output schema as the LLM tagger."""
import re
from . import sources as S

ROLE_RULES = [
    ("AI / ML", r"machine learning|\bml\b|\bai\b|genai|deep learning|nlp|computer vision|research (engineer|scientist)|data scientist|llm"),
    ("Data & Analytics", r"data (analyst|engineer|analytics)|analytics|business intelligence|\bbi\b|\bsql\b|reporting"),
    ("Security / IT / DevOps", r"devops|\bsre\b|site reliability|security|infosec|sysadmin|system admin|network|cloud engineer|it support|infrastructure"),
    ("Software Engineering", r"software|developer|\bsde\b|engineer(?!ing manager)|backend|frontend|full[- ]?stack|\bqa\b|\bsdet\b|android|\bios\b|web"),
    ("Product Management", r"product (manager|management|analyst|owner)|\bapm\b"),
    ("Design / UX", r"design|\bux\b|\bui\b|creative"),
    ("Marketing & Growth", r"marketing|growth|seo|brand|social media|campaign|community"),
    ("Sales & Business Development", r"sales|business development|\bbdm?\b|account executive|inside sales|relationship manager|field"),
    ("Customer Support / Success", r"support|customer|success|service desk|call center|telecall"),
    ("HR & Recruiting", r"recruit|talent|\bhr\b|human resources|people"),
    ("Finance & Accounting", r"financ|account|audit|tax|payroll|credit|risk"),
    ("Operations & Supply Chain", r"operations|supply chain|logistics|procurement|warehouse|delivery|store|\bops\b|plant|production"),
    ("Content & Writing", r"content|writer|editor|copy"),
    ("Hardware / Electrical / Mechanical", r"hardware|electrical|mechanical|electronics|embedded|firmware|\bvlsi\b|manufactur"),
    ("Legal & Compliance", r"legal|compliance|counsel|paralegal"),
]
CITY_RULES = [
    ("Bengaluru", r"bengaluru|bangalore"), ("Mumbai", r"mumbai|thane|navi mumbai"), ("Pune", r"pune"),
    ("Hyderabad", r"hyderabad"), ("Delhi NCR", r"delhi|gurgaon|gurugram|noida|faridabad|ghaziabad"),
    ("Chennai", r"chennai"), ("Kolkata", r"kolkata"), ("Ahmedabad", r"ahmedabad"),
]


def tag(p):
    t, loc, d = p["title"].lower(), p["location_raw"].lower(), p["description"]
    role = next((r for r, rx in ROLE_RULES if re.search(rx, t)), "Other")
    city = next((c for c, rx in CITY_RULES if re.search(rx, loc)), None)
    if not city:
        city = "Remote (India)" if "remote" in loc else "Other India"
    y = S.min_years(d)
    intern = bool(re.search(r"\b(intern|internship|trainee|apprentice)s?\b", t))
    fresher = bool(S.TITLE_ENTRY_RE.search(p["title"]) or S.DESC_ENTRY_RE.search(d[:3000]))
    if intern:
        jt, ok = "Internship", True
    elif y is not None and y >= 3:
        jt, ok = "Not entry-level", False
    elif fresher or (y is not None and y <= 1):
        jt, ok = "Full-time (fresher / 0-1 yr)", True
    elif y == 2:
        jt, ok = "Full-time (1-2 yrs)", True
    else:
        jt, ok = "Not entry-level", False        # no evidence of entry level -> be conservative
    return {"id": p["_h"], "role": role, "city": city, "job_type": jt, "fresher_ok": ok,
            "min_years": 0 if intern else y, "confidence": 0.5, "tagger": "rules"}
