import hashlib
import re
from datetime import datetime, timezone

from typing import Optional

def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def make_job_id(agency: str, title: str, source_url: str) -> str:
    raw = f"{agency}|{title}|{source_url}".lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def extract_salary(text: str | None) -> str:
    text = clean_text(text)
    if not text:
        return ""

    patterns = [
        r"\$\s*\d{2,3},?\d{3}(?:\.\d{2})?\s*[-–]\s*\$?\s*\d{2,3},?\d{3}(?:\.\d{2})?",
        r"\$\s*\d{2,3},?\d{3}(?:\.\d{2})?",
        r"\$\s*\d{2,3}(?:\.\d{2})?\s*/\s*hour",
        r"\$\s*\d{2,3}(?:\.\d{2})?\s*per\s*hour",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)

    return ""


def classify_category(title: str, text: str = "") -> str:
    combined = f"{title} {text}".lower()

    category_keywords = {
        "Planning": ["planner", "planning", "service planning", "transportation planning", "development"],
        "Operations": ["operations", "dispatcher", "control center", "train operator", "bus operator", "station", "depot"],
        "Scheduling": ["scheduler", "scheduling", "timetable", "run cut", "hastus"],
        "Data / Analytics": ["data", "analyst", "analytics", "business intelligence", "reporting", "sql", "python"],
        "Engineering": ["engineer", "engineering", "signal", "track", "civil", "electrical", "mechanical", "architecture"],
        "Maintenance": ["maintenance", "mechanic", "technician", "maintainer", "repair", "facilities"],
        "IT / Digital": ["software", "developer", "systems", "cybersecurity", "information technology", "it ", "technology"],
        "Finance / Budget": ["finance", "budget", "accounting", "procurement", "contract", "purchasing"],
        "Safety / Compliance": ["safety", "compliance", "risk", "security", "police", "law enforcement"],
        "Customer Experience": ["customer", "communications", "public information", "community engagement", "lost & found"],
        "Executive / Administration": ["director", "executive", "administrator", "manager", "chief", "superintendent"],
    }

    scores = {}
    for category, keywords in category_keywords.items():
        score = 0
        for keyword in keywords:
            if keyword in combined:
                score += 3 if keyword in title.lower() else 1
        if score:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)

    return "Other"


def infer_seniority(title: str, text: str = "") -> str:
    title_lower = title.lower()
    combined = f"{title} {text}".lower()

    if any(term in combined for term in ["intern", "internship", "apprentice", "fellowship"]):
        return "Internship / Early Career"
    if any(term in title_lower for term in ["chief", "executive", "vice president", "avp", "deputy general counsel"]):
        return "Executive"
    if any(term in title_lower for term in ["director", "superintendent", "general manager", "senior manager"]):
        return "Senior Leadership"
    if any(term in title_lower for term in ["manager", "supervisor", "foreman", "lead"]):
        return "Manager / Supervisor"
    if any(term in title_lower for term in ["senior", "principal", "specialist", "administrator"]):
        return "Experienced Professional"
    if any(term in title_lower for term in ["assistant", "associate", "trainee", "level 1"]):
        return "Entry / Associate"

    return "Professional"


def normalize_job(
    title: str,
    agency: str,
    city: str,
    state: str,
    source_url: str,
    platform: str,
    salary_text: str | None = None,
    posted_date: str | None = None,
    closing_date: str | None = None,
    category: str | None = None,
    description: str | None = None,
    raw_context: str | None = None,
    extra_fields: dict | None = None,
) -> dict:
    title = clean_text(title)
    source_url = clean_text(source_url)
    description = clean_text(description)
    raw_context = clean_text(raw_context)
    salary_text = clean_text(salary_text) or extract_salary(raw_context or description)
    category_text = raw_context or description
    category = category or classify_category(title, category_text)
    seniority = infer_seniority(title, category_text)

    job = {
        "job_id": make_job_id(agency, title, source_url),
        "title": title,
        "agency": agency,
        "city": city,
        "state": state,
        "source_url": source_url,
        "platform": platform,
        "salary_text": salary_text,
        "posted_date": posted_date or "",
        "closing_date": closing_date or "",
        "category": category,
        "description": description,
        "raw_context": raw_context[:1000] if raw_context else "",
        "all_meaningful_info": raw_context,
        "ai_sort_category": category,
        "ai_sort_seniority": seniority,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    if extra_fields:
        job.update(extra_fields)

    return job
