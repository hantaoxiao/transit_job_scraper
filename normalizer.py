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
        r"\$\d{2,3},?\d{3}(?:\.\d{2})?\s*[-–]\s*\$\d{2,3},?\d{3}(?:\.\d{2})?",
        r"\$\d{2,3},?\d{3}(?:\.\d{2})?",
        r"\$\d{2,3}(?:\.\d{2})?\s*/\s*hour",
        r"\$\d{2,3}(?:\.\d{2})?\s*per\s*hour",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)

    return ""


def classify_category(title: str, text: str = "") -> str:
    combined = f"{title} {text}".lower()

    category_keywords = {
        "Planning": ["planner", "planning", "service planning", "transportation planning"],
        "Operations": ["operations", "dispatcher", "control center", "train operator", "bus operator"],
        "Scheduling": ["scheduler", "scheduling", "timetable", "run cut", "hastus"],
        "Data / Analytics": ["data", "analyst", "analytics", "business intelligence", "reporting", "sql", "python"],
        "Engineering": ["engineer", "engineering", "signal", "track", "civil", "electrical", "mechanical"],
        "Maintenance": ["maintenance", "mechanic", "technician", "maintainer", "repair"],
        "IT / Digital": ["software", "developer", "systems", "cybersecurity", "information technology", "it "],
        "Finance / Budget": ["finance", "budget", "accounting", "procurement", "contract"],
        "Safety / Compliance": ["safety", "compliance", "risk", "security", "police"],
        "Customer Experience": ["customer", "communications", "public information", "community engagement"],
        "Executive / Administration": ["director", "executive", "administrator", "manager", "chief"],
    }

    for category, keywords in category_keywords.items():
        if any(keyword in combined for keyword in keywords):
            return category

    return "Other"


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
) -> dict:
    title = clean_text(title)
    source_url = clean_text(source_url)
    description = clean_text(description)
    raw_context = clean_text(raw_context)
    salary_text = clean_text(salary_text) or extract_salary(raw_context or description)
    category = category or classify_category(title, raw_context or description)

    return {
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
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
