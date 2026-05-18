import hashlib
import re
from datetime import datetime, timezone

from typing import Optional

def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def repair_split_money(text: Optional[str]) -> str:
    text = clean_text(text)
    if not text:
        return ""

    text = re.sub(r"\$\s+(?=\d)", "$", text)
    text = re.sub(r"(\$\d[\d,]*)\s+\.\s+(\d{1,2})\b", r"\1.\2", text)
    split_money = re.compile(r"(\$\d[\d,]*)(?:\s+)(\d[\d,]*(?:\.\d+)?)")

    def should_join(left: str, right: str) -> bool:
        left_digits = left.lstrip("$")
        if "," in right:
            return True
        if "," not in left_digits:
            return False
        last_group = left_digits.rsplit(",", 1)[-1]
        return len(last_group) < 3 and right.replace(".", "").isdigit()

    while True:
        repaired = split_money.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}"
                if should_join(match.group(1), match.group(2))
                else match.group(0)
            ),
            text,
        )
        if repaired == text:
            return repaired
        text = repaired


def clean_date_text(text: Optional[str]) -> str:
    text = clean_text(text)
    if not text:
        return ""

    status_match = re.search(r"\b(continuous|open until filled|apply immediately)\b", text, flags=re.IGNORECASE)
    if status_match and status_match.start() < 40:
        return status_match.group(1).title()

    numeric_date = re.search(
        r"\b\d{1,2}/\d{1,2}/\d{4}",
        text,
        flags=re.IGNORECASE,
    )
    if numeric_date:
        return clean_text(numeric_date.group(0))

    month_date = re.search(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
        r"\d{1,2},\s+\d{4}",
        text,
        flags=re.IGNORECASE,
    )
    if month_date:
        return clean_text(month_date.group(0))

    return text if len(text) <= 48 else ""


def make_job_id(agency: str, title: str, source_url: str) -> str:
    raw = f"{agency}|{title}|{source_url}".lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def extract_salary(text: Optional[str]) -> str:
    text = repair_split_money(text)
    if not text:
        return ""
    text = re.sub(r"\bCompensatio\s+n\b", "Compensation", text, flags=re.IGNORECASE)
    text = re.sub(r"\$\s*(\d{1,3})\s*,\s*(\d{3})", r"$\1,\2", text)
    benefit_terms = (
        r"tuition|reimbursement|benefits?|retirement|401a?|457b?|paid time off|holidays?|"
        r"insurance|employee assistance|medical|dental|vision|wellness|dependent care"
    )

    def is_benefit_context(match: re.Match) -> bool:
        context = text[max(0, match.start() - 90) : match.end() + 90]
        has_benefit_language = re.search(benefit_terms, context, flags=re.IGNORECASE)
        has_pay_label = re.search(
            r"\b(salary range|pay range|starting salary|base salary|annual salary|hourly rate|"
            r"pay rate|starting pay|wage progression)\b",
            context,
            flags=re.IGNORECASE,
        )
        return bool(has_benefit_language and not has_pay_label)

    stop_labels = (
        r"deadline|opening date|closing date|job grade|dept/div|department|location|regulated|"
        r"union affiliation|job description|description|overall description|specific responsibilities|"
        r"qualifications|requirements|benefits|why join|nearest major|apply now|find similar jobs|"
        r"job location|additional|reports to|responsibilities|summary|interview selection process"
    )

    labeled_salary_range = re.search(
        r"\bsalary\s+range\s*(?:is|:)?\s*-?\s*(\$\s*\d[\d,.]*\s*[kK]?(?:\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?)?(?:\s*(?:hourly|annually|per\s+hour|/hour|/hr))?)",
        text,
        flags=re.IGNORECASE,
    )
    if labeled_salary_range:
        return clean_text(labeled_salary_range.group(1))

    labeled_salary = re.search(
        r"\bsalary\s*:\s*(\$\s*\d[\d,.]*\s*[kK]?(?:\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?)?(?:\s*(?:hourly|annually|per\s+hour|/hour|/hr))?)",
        text,
        flags=re.IGNORECASE,
    )
    if labeled_salary:
        return clean_text(labeled_salary.group(1))

    pay_begins_range = re.search(
        r"\bpay\s+begins\s+at\s*(\$\s*\d[\d,.]*)\s*(?:/|per)?\s*(hour|hr)?"
        r".{0,160}?\bincreasing\s+to\s*(\$\s*\d[\d,.]*)\s*(?:/|per)?\s*(hour|hr)?",
        text,
        flags=re.IGNORECASE,
    )
    if pay_begins_range:
        unit = "per hour" if pay_begins_range.group(2) or pay_begins_range.group(4) else ""
        return clean_text(f"{pay_begins_range.group(1)} - {pay_begins_range.group(3)} {unit}")

    expected_compensation = re.search(
        r"\bexpected\s+compensation\s+range\b.+?\bMinimum:\s*(\$\s*\d[\d,.]*)"
        r".+?\bMaximum:\s*(\$\s*\d[\d,.]*)",
        text,
        flags=re.IGNORECASE,
    )
    if expected_compensation:
        return clean_text(f"{expected_compensation.group(1)} - {expected_compensation.group(2)}")

    bare_annual_salary = re.search(
        r"\b(\d{5,6}(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d{5,6}(?:\.\d+)?)\s+per\s+year\s+salary\b",
        text,
        flags=re.IGNORECASE,
    )
    if bare_annual_salary:
        return clean_text(f"Compensation: {bare_annual_salary.group(1)} - {bare_annual_salary.group(2)} per year")

    annual_amount = re.search(
        r"(\$\s*\d[\d,.]*\s*[kK]?\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?\s+Annually|\$\s*\d[\d,.]*\s*[kK]?\s+Annually)",
        text,
        flags=re.IGNORECASE,
    )
    if annual_amount and not is_benefit_context(annual_amount):
        return clean_text(annual_amount.group(1))

    hourly_rate = re.search(
        rf"\b(?:hourly\s+rate|hourly\s+range|starting\s+pay\s+rate|pay\s+rate|rate\s+of\s+pay)\s*:?\s*-?\s*(.+?)(?=\s+(?:{stop_labels})\s*:?\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if hourly_rate and "$" in hourly_rate.group(1):
        section = hourly_rate.group(1)
        money_matches = list(re.finditer(r"\$\s*\d[\d,.]*\s*[kK]?(?:\s*\([^)]*\))?", section))
        if money_matches:
            return clean_text(f"Hourly Rate: {section[:money_matches[-1].end()]}")

    hourly_range = re.search(
        r"\$\s*\d[\d,.]*\s*/?\s*(?:hr|hour)\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*/?\s*(?:hr|hour)",
        text,
        flags=re.IGNORECASE,
    )
    if hourly_range:
        return clean_text(hourly_range.group(0))

    starting_salary = re.search(
        r"\bstarting salary\s*(?:of|is|:)?\s*-?\s*(\$\s*\d[\d,.]*)",
        text,
        flags=re.IGNORECASE,
    )
    if starting_salary:
        return clean_text(starting_salary.group(1))

    explicit_range = re.search(
        r"\bsalary range\s*(?:is|:)?\s*-?\s*(\$\s*\d[\d,.]*\s*[kK]?\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?)",
        text,
        flags=re.IGNORECASE,
    )
    if explicit_range:
        return clean_text(explicit_range.group(1))

    currency_range = re.search(
        r"\$\s*\d[\d,.]*\s*[kK]?\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?",
        text,
        flags=re.IGNORECASE,
    )
    if (
        currency_range
        and not is_benefit_context(currency_range)
        and re.search(r"\b(salary|compensation|posted range|pay|rate|wage)\b", text, flags=re.IGNORECASE)
    ):
        return clean_text(currency_range.group(0))

    salary_section = re.search(
        rf"(?:starting salary|salary range|pay range|starting pay rate|pay rate|hourly rate|annual salary|base salary|earnings potential|wage progression|compensation)\s*(?:is|:|-)?\s*-?\s*(.+?)(?=\s+(?:{stop_labels})\s*:?\b|$)",
        text,
        flags=re.IGNORECASE,
    ) or re.search(
        rf"\bsalary\s*(?:is|:|-)?\s*-?\s*(.+?)(?=\s+(?:{stop_labels})\s*:?\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if salary_section:
        section = salary_section.group(1)
        money_matches = list(re.finditer(r"\$\s*\d[\d,.]*\s*[kK]?", section))
        if not money_matches:
            money_matches = list(re.finditer(r"\b\d{2,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{2,3}\.\d{2,6}\b", section))
        if money_matches:
            end = money_matches[-1].end()
            unit_match = re.match(r"\s*(?:per\s+hour|/hour|/hr|hourly)\b", section[end:], flags=re.IGNORECASE)
            if unit_match:
                end += unit_match.end()
            extracted = clean_text(section[:end])
            if "$" not in extracted:
                extracted = f"Compensation: {extracted}"
            return extracted

    pre_description = re.search(
        r"(.+?)(?=\s+overall description\b)",
        text,
        flags=re.IGNORECASE,
    )
    if pre_description and "$" in pre_description.group(1):
        section = pre_description.group(1)
        money_matches = list(re.finditer(r"\$?\s*\d[\d,.]*\s*[kK]?(?:\s*/?\s*(?:hr|hour))?", section, flags=re.IGNORECASE))
        if money_matches:
            start = section.find("$")
            end = money_matches[-1].end()
            candidate_match = re.search(r"\$\s*\d[\d,.]*\s*[kK]?", section[start:end])
            local_context = section[max(0, start - 90) : min(len(section), end + 90)]
            if not candidate_match or not re.search(benefit_terms, local_context, flags=re.IGNORECASE):
                return clean_text(section[start:end])

    if len(text) > 180:
        return ""

    patterns = [
        r"\$\s*\d[\d,.]*\s*[kK]?\s*(?:[-–]|to)\s*\$?\s*\d[\d,.]*\s*[kK]?(?:\s*(?:/|per)\s*(?:hour|hr))?",
        r"\$\s*\d{2,3}(?:\.\d{2})?\s*/\s*hour",
        r"\$\s*\d{2,3}(?:\.\d{2})?\s*/\s*hr",
        r"\$\s*\d{2,3}(?:\.\d{2})?\s*per\s*hour",
        r"\$\s*\d[\d,.]*\s*[kK]?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and not is_benefit_context(match):
            return match.group(0)

    return ""


def salary_has_money(text: Optional[str]) -> bool:
    return bool(re.search(r"\$\s*\d", clean_text(text)))


def _parse_money(value: str) -> Optional[float]:
    multiplier = 1000 if re.search(r"[kK]\s*$", value.strip()) else 1
    value = value.replace("$", "").replace(",", "").strip()
    value = re.sub(r"[kK]\s*$", "", value).strip()
    value = value.rstrip(".")

    if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", value):
        value = value.replace(".", ",").replace(",", "")

    try:
        return float(value) * multiplier
    except ValueError:
        return None


def _money_values(text: str) -> list[float]:
    values = []
    dollar_tokens = re.findall(r"\$\s*\d[\d,.]*\s*[kK]?", text)
    bare_range_tokens = re.findall(
        r"\$\s*\d[\d,.]*\s*[kK]?\s*(?:[-–]|to|min-?)\s*\$?\s*(\d[\d,.]*\s*[kK]?)",
        text,
        flags=re.IGNORECASE,
    )
    labeled_bare_tokens = []
    if re.search(r"\b(salary|compensation|pay rate|hourly rate|rate of pay)\b", text, flags=re.IGNORECASE):
        labeled_bare_tokens = re.findall(
            r"\b\d{2,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{2,3}\.\d{2,6}\b|\b\d{5,6}(?:\.\d+)?\b",
            text,
        )

    for token in [*dollar_tokens, *bare_range_tokens, *labeled_bare_tokens]:

        value = _parse_money(token)
        if value is None:
            continue
        if value < 10:
            continue
        values.append(value)

    return values


def _format_money(value: float, unit: str) -> str:
    if unit == "hourly":
        return f"${value:,.2f}/hr"
    if value < 1000 and value != round(value):
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def _salary_range_display(salary_min: float, salary_max: float, unit: str) -> str:
    if salary_min == salary_max:
        return _format_money(salary_min, unit)
    return f"{_format_money(salary_min, unit)} - {_format_money(salary_max, unit)}"


def parse_salary(salary_text: Optional[str]) -> dict:
    text = repair_split_money(salary_text)
    if not text:
        return {
            "salary_display": "Salary not listed",
            "salary_is_listed": False,
            "salary_min": "",
            "salary_max": "",
            "salary_midpoint": "",
            "salary_range_display": "Salary not listed",
            "salary_unit": "unknown",
            "salary_annual_min_est": "",
            "salary_annual_max_est": "",
            "salary_annual_mid_est": "",
            "salary_is_comparable": False,
            "salary_confidence": "missing",
        }

    normalized = text.lower()
    values = _money_values(text)

    if not values:
        return {
            "salary_display": text,
            "salary_is_listed": True,
            "salary_min": "",
            "salary_max": "",
            "salary_midpoint": "",
            "salary_range_display": text,
            "salary_unit": "unknown",
            "salary_annual_min_est": "",
            "salary_annual_max_est": "",
            "salary_annual_mid_est": "",
            "salary_is_comparable": False,
            "salary_confidence": "low",
        }

    salary_min = min(values)
    salary_max = max(values)
    salary_midpoint = round((salary_min + salary_max) / 2, 2)
    is_hourly = bool(re.search(r"\b(hour|hourly|hr)\b|/\s*h", normalized))
    is_annual = (
        bool(re.search(r"\b(year|annual|annually|salary|per annum)\b", normalized))
        or salary_max >= 1000
    )

    if salary_max < 1000 and (is_hourly or not is_annual or re.search(r"\bannually\b", normalized)):
        unit = "hourly"
        annual_min = round(salary_min * 2080)
        annual_max = round(salary_max * 2080)
        annual_mid = round(salary_midpoint * 2080)
        comparable = True
        confidence = "medium"
    elif is_annual:
        unit = "annual"
        annual_min = round(salary_min)
        annual_max = round(salary_max)
        annual_mid = round(salary_midpoint)
        comparable = True
        confidence = "high"
    else:
        unit = "unknown"
        annual_min = ""
        annual_max = ""
        annual_mid = ""
        comparable = False
        confidence = "low"

    range_display = _salary_range_display(salary_min, salary_max, unit)

    return {
        "salary_display": range_display,
        "salary_is_listed": True,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_midpoint": salary_midpoint,
        "salary_range_display": range_display,
        "salary_unit": unit,
        "salary_annual_min_est": annual_min,
        "salary_annual_max_est": annual_max,
        "salary_annual_mid_est": annual_mid,
        "salary_is_comparable": comparable,
        "salary_confidence": confidence,
    }


def compute_data_quality(job: dict) -> dict:
    checks = {
        "has_title": bool(job.get("title")),
        "has_agency": bool(job.get("agency")),
        "has_location": bool(job.get("city") and job.get("state")),
        "has_source_url": bool(job.get("source_url")),
        "has_category": bool(job.get("category") and job.get("category") != "Other"),
        "has_seniority": bool(job.get("ai_sort_seniority")),
        "has_salary": bool(job.get("salary_is_listed")),
        "has_posted_date": bool(job.get("posted_date")),
        "has_closing_date": bool(job.get("closing_date")),
        "has_description": bool(job.get("description") or job.get("all_meaningful_info")),
    }
    score = round(sum(checks.values()) / len(checks) * 100)

    if score >= 80 and checks["has_salary"]:
        label = "Complete"
    elif score >= 55:
        label = "Partial"
    else:
        label = "Minimal"

    missing = [
        label.replace("has_", "")
        for label, present in checks.items()
        if not present
    ]

    return {
        "data_quality": label,
        "data_completeness_score": score,
        "missing_fields": ", ".join(missing),
    }


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

    if re.search(r"\b(intern|internship|apprentice|fellowship)\b", combined):
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
    salary_text: Optional[str] = None,
    posted_date: Optional[str] = None,
    closing_date: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    raw_context: Optional[str] = None,
    extra_fields: Optional[dict] = None,
) -> dict:
    title = clean_text(title)
    source_url = clean_text(source_url)
    description = clean_text(description)
    raw_context = clean_text(raw_context)
    salary_text = clean_text(salary_text)
    posted_date = clean_date_text(posted_date)
    closing_date = clean_date_text(closing_date)
    if not salary_has_money(salary_text):
        salary_text = extract_salary(raw_context or description) or salary_text
    salary_fields = parse_salary(salary_text)
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
        **salary_fields,
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

    job.update(compute_data_quality(job))

    return job
