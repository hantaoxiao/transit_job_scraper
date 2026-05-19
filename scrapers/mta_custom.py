import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import local
from typing import Optional
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests as curl_requests

from normalizer import clean_text, extract_salary, normalize_job, parse_salary, repair_split_money
from scrapers.detail_cache import cached_job, has_cached_detail


BASE_URL = "https://careers.mta.org"
SEARCH_URL = "https://careers.mta.org/search/jobs/in"
SEARCH_JSON_URL = "https://careers.mta.org/search/jobs.json"
DEFAULT_DETAIL_WORKERS = 8
DEFAULT_PER_PAGE = 100
DEFAULT_MAX_PAGES = 20
DEFAULT_LISTING_DELAY = 0.25
DEFAULT_DETAIL_DELAY = 0.0
DEFAULT_REQUEST_TIMEOUT = 30

DETAIL_LABELS = (
    "Job ID",
    "Business Unit",
    "Location",
    "Regular/Temporary",
    "Department",
    "Date Posted",
    "Title",
    "First Date of Posting",
    "Authority",
    "Division/Unit",
    "Reports to",
    "Reporting Manager (If Applicable)",
    "Work Location",
    "Hours of Work",
    "Job Family",
    "Grade",
    "Salary Range",
    "Compensation",
    "Salary",
    "Deadline",
    "Deadline (if Applicable)",
    "Metro-North Posting Date",
    "Metro-North Closing Date",
)

DETAIL_KEY_MAP = {
    "AGENCY": "business_unit",
    "AUTHORITY": "business_unit",
    "BUSINESS UNIT": "business_unit",
    "DATE POSTED": "posted_date",
    "DEADLINE": "closing_date",
    "DEADLINE IF APPLICABLE": "closing_date",
    "DEPARTMENT": "department",
    "DEPT DIV": "department",
    "DIVISION UNIT": "division_unit",
    "FIRST DATE OF POSTING": "posted_date",
    "GRADE": "job_grade",
    "HOURS OF WORK": "hours_of_work",
    "JOB FAMILY": "job_family",
    "JOB ID": "mta_job_id",
    "JOB TITLE": "detail_job_title",
    "LOCATION": "detail_location",
    "METRO NORTH CLOSING DATE": "closing_date",
    "METRO NORTH POSTING DATE": "posted_date",
    "REGULAR TEMPORARY": "employment_type",
    "REPORTING MANAGER IF APPLICABLE": "reports_to",
    "REPORTS TO": "reports_to",
    "SALARY": "salary_text",
    "SALARY RANGE": "salary_text",
    "COMPENSATION": "salary_text",
    "TITLE": "detail_job_title",
    "WORK LOCATION": "work_location",
}

_THREAD_LOCAL = local()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


DETAIL_WORKERS = _env_int("MTA_DETAIL_WORKERS", DEFAULT_DETAIL_WORKERS)
REQUEST_TIMEOUT = _env_int("MTA_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
PER_PAGE = _env_int("MTA_CAREERS_PER_PAGE", DEFAULT_PER_PAGE)
MAX_PAGES = _env_int("MTA_CAREERS_MAX_PAGES", DEFAULT_MAX_PAGES)
LISTING_DELAY = _env_float("MTA_CAREERS_DELAY", DEFAULT_LISTING_DELAY)
DETAIL_DELAY = _env_float("MTA_DETAIL_DELAY", DEFAULT_DETAIL_DELAY)
CURL_IMPERSONATE = os.getenv("MTA_CURL_IMPERSONATE", "chrome124")
FALLBACK_IMPERSONATES = tuple(
    dict.fromkeys(
        value.strip()
        for value in os.getenv("MTA_CURL_IMPERSONATES", f"{CURL_IMPERSONATE},safari17_0").split(",")
        if value.strip()
    )
)
JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://careers.mta.org/search/jobs/in?page=1&per_page=100",
}
DETAIL_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://careers.mta.org/search/jobs/in?page=1&per_page=100",
}
STATE_ABBREVIATIONS = {
    "Connecticut": "CT",
    "District of Columbia": "DC",
    "New Jersey": "NJ",
    "New York": "NY",
}

_ACTIVE_IMPERSONATE = FALLBACK_IMPERSONATES[0] if FALLBACK_IMPERSONATES else CURL_IMPERSONATE


def _new_careers_session(impersonate: Optional[str] = None):
    return curl_requests.Session(impersonate=impersonate or _ACTIVE_IMPERSONATE)


def _set_active_impersonate(impersonate: str) -> None:
    global _ACTIVE_IMPERSONATE
    _ACTIVE_IMPERSONATE = impersonate
    if hasattr(_THREAD_LOCAL, "session"):
        delattr(_THREAD_LOCAL, "session")


def _thread_session():
    if not hasattr(_THREAD_LOCAL, "session"):
        _THREAD_LOCAL.session = _new_careers_session()
    return _THREAD_LOCAL.session


def _warm_up_session(session) -> None:
    print("Warming up MTA careers session...")
    try:
        session.get(BASE_URL, timeout=15)
        time.sleep(1.0)
    except Exception as exc:
        print(f"Warning: MTA careers warm-up failed ({exc}), continuing.")
        return


def _careers_page_url(page: int, per_page: int = PER_PAGE) -> str:
    return f"{SEARCH_URL}?{urlencode({'page': page, 'per_page': per_page})}"


def _careers_json_url(page: int, per_page: int = PER_PAGE) -> str:
    return f"{SEARCH_JSON_URL}?{urlencode({'page': page, 'per_page': per_page})}"


def _parse_mta_date(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""

    for date_format in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def _extract_careers_field(card_text: str, label: str) -> str:
    labels = r"Job ID|Location|Department|Date Posted"
    pattern = rf"{re.escape(label)}:\s*(.*?)(?=\s+(?:{labels}):|$)"
    match = re.search(pattern, card_text, flags=re.IGNORECASE)
    if not match:
        return ""
    return clean_text(match.group(1)).rstrip(",")


def _find_careers_job_card(anchor: Tag) -> Optional[Tag]:
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        text = clean_text(parent.get_text(" ", strip=True))
        if "Job ID:" in text and "Date Posted:" in text and len(text) < 2500:
            return parent
    return None


def _parse_careers_search_page(html: str, agency: dict, page_url: str, normalize: bool = False) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    summaries = []
    seen_ids = set()

    for anchor in soup.find_all("a", href=True):
        source_url = urljoin(page_url, anchor.get("href", ""))
        title = clean_text(anchor.get_text(" ", strip=True))
        if "/jobs/" not in source_url or not title:
            continue

        card = _find_careers_job_card(anchor)
        if card is None:
            continue

        card_text = clean_text(card.get_text(" ", strip=True))
        job_id = _extract_careers_field(card_text, "Job ID")
        if not job_id or job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        location = _extract_careers_field(card_text, "Location")
        department = _extract_careers_field(card_text, "Department")
        posted_date = _extract_careers_field(card_text, "Date Posted")
        raw_context = clean_text(
            " ".join(
                value
                for value in [
                    title,
                    f"Job ID: {job_id}",
                    f"Location: {location}" if location else "",
                    f"Department: {department}" if department else "",
                    f"Date Posted: {posted_date}" if posted_date else "",
                ]
                if value
            )
        )
        summary = {
            "title": title,
            "source_url": source_url,
            "location": location,
            "department": department,
            "posted_date": posted_date,
            "posted_date_iso": _parse_mta_date(posted_date),
            "raw_context": raw_context,
            "mta_job_id": job_id,
            "mta_careers_url": source_url,
            "requisition_id": job_id,
        }
        summaries.append(_build_mta_job(summary, agency) if normalize else summary)

    return summaries


def _entry_location_text(location: dict) -> str:
    if not isinstance(location, dict):
        return ""

    parts = [
        clean_text(location.get("locality")),
        clean_text(location.get("region_abbr") or location.get("region_full")),
        clean_text(location.get("country")),
    ]
    return ", ".join(part for part in parts if part)


def _entry_source_url(entry: dict) -> str:
    entry_id = clean_text(entry.get("id") or entry.get("talemetry_job_id"))
    permalink = clean_text(entry.get("permalink"))
    if entry_id and permalink:
        return f"{BASE_URL}/jobs/{entry_id}-{permalink}"
    if entry_id:
        return f"{BASE_URL}/jobs/{entry_id}"
    return ""


def _parse_careers_search_json(data: dict, agency: dict, normalize: bool = False) -> list[dict]:
    summaries = []
    seen_ids = set()

    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue

        internal_id = clean_text(entry.get("talemetry_job_id") or entry.get("id"))
        title = clean_text(entry.get("title"))
        source_url = _entry_source_url(entry)
        if not internal_id or not title or not source_url or internal_id in seen_ids:
            continue
        seen_ids.add(internal_id)

        location = _entry_location_text(entry.get("location") or {})
        raw_context = clean_text(
            " ".join(
                value
                for value in [
                    title,
                    f"Talemetry Job ID: {internal_id}",
                    f"Location: {location}" if location else "",
                ]
                if value
            )
        )
        summary = {
            "title": title,
            "source_url": source_url,
            "location": location,
            "department": "",
            "posted_date": "",
            "posted_date_iso": "",
            "raw_context": raw_context,
            "mta_job_id": internal_id,
            "mta_internal_id": internal_id,
            "mta_careers_url": source_url,
            "requisition_id": internal_id,
        }
        summaries.append(_build_mta_job(summary, agency) if normalize else summary)

    return summaries


def _blocked_listing_error(page_url: str, status_code: int) -> RuntimeError:
    return RuntimeError(
        f"MTA careers JSON listing returned {status_code} for {page_url}. "
        "The request was blocked before parsing; on GitHub-hosted Actions this usually means "
        "Cloudflare rejected the runner IP or TLS fingerprint."
    )


def _scrape_careers_json_summaries(session, agency: dict) -> list[dict]:
    summaries_by_id = {}
    total_entries = None

    for page in range(1, MAX_PAGES + 1):
        page_url = _careers_json_url(page)
        response = session.get(page_url, timeout=REQUEST_TIMEOUT, headers=JSON_HEADERS)
        if getattr(response, "status_code", 200) == 403:
            raise _blocked_listing_error(page_url, response.status_code)
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"MTA careers JSON listing was not valid JSON for {page_url}") from exc

        total_entries = payload.get("total_entries", total_entries)
        page_summaries = _parse_careers_search_json(payload, agency, normalize=False)
        print(
            f"MTA careers JSON listing page={page} jobs_found={len(page_summaries)}"
            + (f" total_entries={total_entries}" if total_entries is not None else "")
        )
        if not page_summaries:
            break

        for summary in page_summaries:
            summaries_by_id[summary["mta_internal_id"]] = summary

        if len(page_summaries) < PER_PAGE or (total_entries and len(summaries_by_id) >= int(total_entries)):
            break

        time.sleep(LISTING_DELAY)

    return list(summaries_by_id.values())


def _scrape_careers_summaries(agency: dict) -> list[dict]:
    last_blocked_error = None

    for impersonate in FALLBACK_IMPERSONATES:
        session = _new_careers_session(impersonate)
        try:
            summaries = _scrape_careers_json_summaries(session, agency)
        except RuntimeError as exc:
            if "MTA careers JSON listing returned 403" not in str(exc):
                raise
            last_blocked_error = exc
            print(f"MTA careers JSON listing blocked with curl_cffi impersonate={impersonate}; trying fallback.")
            continue

        _set_active_impersonate(impersonate)
        if impersonate != CURL_IMPERSONATE:
            print(f"MTA careers JSON listing succeeded with curl_cffi impersonate={impersonate}.")
        return summaries

    if last_blocked_error:
        raise last_blocked_error
    return []


def _canonical_detail_label(label: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", clean_text(label).upper()).strip()


def _detail_key(label: str) -> str:
    return DETAIL_KEY_MAP.get(_canonical_detail_label(label), "")


def _extract_labeled_value(text: str, label: str) -> str:
    label_key = _canonical_detail_label(label)
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    for index, line in enumerate(lines):
        label_match = re.match(r"^(.+?)\s*:\s*(.*)$", line)
        if label_match and _canonical_detail_label(label_match.group(1)) == label_key:
            if label_match.group(2):
                return clean_text(label_match.group(2))
            if index + 1 < len(lines):
                return clean_text(lines[index + 1])
        if _canonical_detail_label(line.rstrip(":")) == label_key and index + 1 < len(lines):
            return clean_text(lines[index + 1])

    return ""


def _extract_labeled_section(text: str, label: str) -> str:
    normalized_text = "\n".join(clean_text(line) for line in text.splitlines() if clean_text(line))
    label_pattern = re.escape(label).replace(r"\ ", r"\s+")
    stop_label_pattern = "|".join(
        re.escape(stop_label).replace(r"\ ", r"\s+")
        for stop_label in DETAIL_LABELS
        if _canonical_detail_label(stop_label) != _canonical_detail_label(label)
    )
    match = re.search(
        rf"(?ims)^\s*{label_pattern}\s*:?\s*(.+?)(?=^\s*(?:{stop_label_pattern})\s*:?\s*$|\Z)",
        normalized_text,
    )
    return clean_text(match.group(1)) if match else ""


def _clean_compensation_section(text: str) -> str:
    text = repair_split_money(text)
    for heading in (
        "Deadline",
        "Summary",
        "Responsibilities",
        "Education and Experience",
        "Desired Skills",
        "Selection Criteria",
        "Selection Method",
        "Other Information",
        "How to Apply",
        "Equal Employment Opportunity",
    ):
        text = re.split(rf"\s+\b{re.escape(heading)}\b(?:\s*:)?", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return clean_text(text)


def _location_to_city_state(location: str, agency: dict) -> tuple[str, str]:
    city = agency["city"]
    state = agency["state"]
    location = clean_text(location)

    if not location:
        return city, state

    location = re.sub(r",?\s*(United States|USA)\s*$", "", location, flags=re.IGNORECASE)
    parts = [part.strip() for part in re.split(r",|\n", location) if part.strip()]
    if parts:
        city = parts[0]
    if len(parts) > 1:
        state_candidate = parts[-1].upper()
        if re.fullmatch(r"[A-Z]{2}", state_candidate):
            state = state_candidate
        elif state_candidate not in {"UNITED STATES", "USA"}:
            state = parts[-1]

    return city, state


def _split_label_value(text: str) -> tuple[str, str]:
    text = clean_text(text)
    if ":" not in text:
        return "", ""
    label, value = text.split(":", 1)
    if not _detail_key(label):
        return "", ""
    return clean_text(label), clean_text(value)


def _store_detail_field(fields: dict, label: str, value: str) -> None:
    key = _detail_key(label)
    value = clean_text(value)
    if key and value:
        fields[key] = value


def _extract_detail_table_fields(container) -> dict:
    fields = {}
    if container is None:
        return fields

    for row in container.select("table tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if not cells:
            continue

        if len(cells) >= 2:
            left_label, left_value = _split_label_value(cells[0])
            right_label, right_value = _split_label_value(cells[1])

            if left_label and left_value:
                _store_detail_field(fields, left_label, left_value)
            elif left_label:
                _store_detail_field(fields, left_label, cells[1])

            if right_label:
                _store_detail_field(fields, right_label, right_value)

            continue

        label, value = _split_label_value(cells[0])
        if label:
            _store_detail_field(fields, label, value)

    return fields


def _detail_text(container) -> str:
    if container is None:
        return ""

    skipped = {
        "Skip to main content",
        "Join our Talent Network",
        "Talent Network",
        "Apply Now",
        "Share Job",
        "Jobs at MTA Headquarters",
    }
    lines = [clean_text(line) for line in container.get_text("\n", strip=True).splitlines()]
    lines = [line for line in lines if line and line not in skipped]
    return "\n".join(lines)


def _supplement_detail_fields_from_text(fields: dict, text: str) -> dict:
    fields = dict(fields)
    for label in DETAIL_LABELS:
        key = _detail_key(label)
        if not key or fields.get(key):
            continue
        value = _extract_labeled_value(text, label)
        if value:
            fields[key] = value
    return fields


def _valid_salary_text(text: str) -> bool:
    parsed = parse_salary(text)
    return bool(parsed.get("salary_is_listed") and "$" in clean_text(text))


def _salary_from_detail(fields: dict, text: str) -> str:
    candidates = [
        fields.get("salary_text", ""),
        _extract_labeled_section(text, "Salary Range"),
        _extract_labeled_section(text, "Compensation"),
        _extract_labeled_section(text, "Salary"),
        extract_salary(text),
    ]

    for candidate in candidates:
        salary_text = _clean_compensation_section(candidate)
        extracted_salary = extract_salary(f"Salary Range: {salary_text}")
        if _valid_salary_text(extracted_salary):
            return extracted_salary
        if _valid_salary_text(salary_text):
            return salary_text
    return ""


def _json_ld_jobposting(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        raw = raw.replace(r"\$", "$")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            return payload
    return {}


def _json_ld_description_text(jobposting: dict) -> str:
    description_html = jobposting.get("description")
    if not description_html:
        return ""
    return _detail_text(BeautifulSoup(description_html, "lxml"))


def _json_ld_location(jobposting: dict) -> str:
    location = jobposting.get("jobLocation")
    if isinstance(location, list):
        location = location[0] if location else {}
    if not isinstance(location, dict):
        return ""

    address = location.get("address")
    if not isinstance(address, dict):
        return ""

    region = clean_text(address.get("addressRegion"))
    region = STATE_ABBREVIATIONS.get(region, region)
    return clean_text(
        ", ".join(
            value
            for value in [address.get("addressLocality"), region, address.get("addressCountry")]
            if clean_text(value)
        )
    )


def _json_ld_identifier(jobposting: dict) -> str:
    identifier = jobposting.get("identifier")
    if isinstance(identifier, dict):
        return clean_text(identifier.get("value"))
    return clean_text(identifier)


def _parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("main") or soup.select_one("article") or soup
    jobposting = _json_ld_jobposting(soup)
    meaningful_text = _detail_text(container)
    structured_text = _json_ld_description_text(jobposting)
    combined_text = "\n".join(text for text in [meaningful_text, structured_text] if text)
    fields = _supplement_detail_fields_from_text(_extract_detail_table_fields(container), combined_text)

    job_id = _json_ld_identifier(jobposting)
    if job_id and not fields.get("mta_job_id"):
        fields["mta_job_id"] = job_id

    posted_date = clean_text(jobposting.get("datePosted"))
    if posted_date and not fields.get("posted_date"):
        fields["posted_date"] = posted_date

    valid_through = clean_text(jobposting.get("validThrough"))
    if valid_through and not fields.get("closing_date"):
        fields["closing_date"] = valid_through

    structured_location = _json_ld_location(jobposting)
    if structured_location and not fields.get("detail_location"):
        fields["detail_location"] = structured_location

    salary_text = _salary_from_detail(fields, combined_text)

    details = {
        "all_meaningful_info": combined_text,
        "full_job_description": combined_text,
        "salary_text": salary_text,
        "detail_location": fields.get("detail_location", ""),
        "business_unit": fields.get("business_unit", ""),
        "department": fields.get("department", ""),
        "division_unit": fields.get("division_unit", ""),
        "employment_type": fields.get("employment_type", ""),
        "reports_to": fields.get("reports_to", ""),
        "work_location": fields.get("work_location", ""),
        "hours_of_work": fields.get("hours_of_work", ""),
        "job_family": fields.get("job_family", ""),
        "job_grade": fields.get("job_grade", ""),
        "posted_date": fields.get("posted_date", ""),
        "closing_date": fields.get("closing_date", ""),
        "mta_job_id": fields.get("mta_job_id", ""),
        "requisition_id": fields.get("mta_job_id", ""),
    }
    return {key: value for key, value in details.items() if value}


def _annual_salary_estimate(parsed_salary: dict) -> float:
    for field in ("salary_annual_max_est", "salary_max"):
        value = parsed_salary.get(field)
        if value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _cached_job_details(job: dict) -> dict:
    detail_keys = [
        "all_meaningful_info",
        "business_unit",
        "closing_date",
        "department",
        "detail_location",
        "division_unit",
        "employment_type",
        "full_job_description",
        "hours_of_work",
        "job_family",
        "job_grade",
        "mta_careers_url",
        "mta_job_id",
        "posted_date",
        "posted_date_iso",
        "requisition_id",
        "reports_to",
        "salary_text",
        "work_location",
    ]
    details = {key: job.get(key, "") for key in detail_keys if job.get(key)}
    if job.get("description") and not details.get("full_job_description"):
        details["full_job_description"] = job["description"]
    if job.get("raw_context") and not details.get("all_meaningful_info"):
        details["all_meaningful_info"] = job["raw_context"]
    if details.get("salary_text"):
        details["salary_text"] = _clean_compensation_section(details["salary_text"])

    context = details.get("all_meaningful_info") or details.get("full_job_description") or ""
    extracted = extract_salary(context)
    if not extracted:
        return details

    current_salary = parse_salary(details.get("salary_text", ""))
    extracted_salary = parse_salary(extracted)
    if not extracted_salary.get("salary_is_comparable"):
        return details

    current_estimate = _annual_salary_estimate(current_salary)
    extracted_estimate = _annual_salary_estimate(extracted_salary)
    if (
        not current_salary.get("salary_is_comparable")
        or current_estimate < 30000
        or extracted_estimate > current_estimate * 2
    ):
        details["salary_text"] = extracted

    return details


def _fetch_detail(source_url: str) -> dict:
    if DETAIL_DELAY:
        time.sleep(DETAIL_DELAY)
    try:
        response = _thread_session().get(source_url, timeout=REQUEST_TIMEOUT, headers=DETAIL_HEADERS)
        response.raise_for_status()
    except Exception:
        return {}

    return _parse_detail_page(response.text)


def _build_mta_job(summary: dict, agency: dict, details: Optional[dict] = None) -> dict:
    details = details or {}
    location = details.get("detail_location") or summary.get("location", "")
    city, state = _location_to_city_state(location, agency)
    description = details.get("full_job_description") or details.get("all_meaningful_info") or summary.get("raw_context", "")
    raw_context = clean_text(
        " ".join(value for value in [summary.get("raw_context", ""), details.get("all_meaningful_info", "")] if value)
    )
    posted_date = details.get("posted_date") or summary.get("posted_date", "")
    posted_date_iso = summary.get("posted_date_iso") or _parse_mta_date(posted_date)

    extra_fields = {
        key: value
        for key, value in {
            **details,
            "department": details.get("department") or summary.get("department", ""),
            "mta_careers_url": summary.get("mta_careers_url") or summary.get("source_url", ""),
            "mta_job_id": details.get("mta_job_id") or summary.get("mta_job_id", ""),
            "posted_date_iso": posted_date_iso,
            "requisition_id": details.get("requisition_id") or summary.get("requisition_id") or summary.get("mta_job_id", ""),
        }.items()
        if value and key not in {"salary_text", "full_job_description", "all_meaningful_info", "detail_location"}
    }

    return normalize_job(
        title=summary["title"],
        agency=agency["agency"],
        city=city,
        state=state,
        source_url=summary["source_url"],
        platform=agency["platform"],
        salary_text=details.get("salary_text", ""),
        posted_date=posted_date,
        closing_date=details.get("closing_date", ""),
        description=description,
        raw_context=raw_context,
        extra_fields=extra_fields,
    )


def scrape_mta(agency: dict) -> list[dict]:
    summaries = _scrape_careers_summaries(agency)
    if not summaries:
        return []

    for summary in summaries:
        summary["cached"] = cached_job(
            agency["agency"],
            source_url=summary["source_url"],
            requisition_id=summary.get("mta_job_id", ""),
            title=summary["title"],
        )

    pending = [summary for summary in summaries if not has_cached_detail(summary["cached"])]
    details_by_url = {}
    if pending:
        print(f"Fetching live MTA details for {len(pending)} jobs.")
        workers = min(DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_fetch_detail, summary["source_url"]): summary for summary in pending}
            for future in as_completed(futures):
                summary = futures[future]
                details_by_url[summary["source_url"]] = future.result()

    jobs = []
    for summary in summaries:
        details = details_by_url.get(summary["source_url"])
        if not details:
            details = _cached_job_details(summary["cached"])
        jobs.append(_build_mta_job(summary, agency, details))

    return jobs
