import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

BAD_TITLES = {
    "apply",
    "apply by email",
    "refer a candidate",
    "more information",
    "previous",
    "next",
    "view all jobs",
}

SEARCH_API = "/careersection/rest/jobboard/searchjobs"


def _candidate_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    urls = [url]
    if "jobsearch.ftl" in parsed.path:
        urls.append(url.replace("jobsearch.ftl", "joblist.ftl"))
        urls.append(url.replace("jobsearch.ftl", "moresearch.ftl"))
    return urls


def _portal_number(html: str) -> str:
    match = re.search(r"portal=(\d+)", html)
    return match.group(1) if match else ""


def _search_api_url(base_url: str, portal: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}{SEARCH_API}?lang=en&portal={portal}"


def _detail_url(base_url: str, job_id: str) -> str:
    return urljoin(base_url, f"jobdetail.ftl?job={job_id}")


def _search_payload(multiline: bool, page: int) -> dict:
    return {
        "multilineEnabled": multiline,
        "pageNo": page,
    }


def _post_search(session: requests.Session, api_url: str, multiline: bool, page: int) -> dict:
    response = session.post(
        api_url,
        headers={
            **HEADERS,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "tz": "GMT-04:00",
            "tzname": "America/New_York",
        },
        json=_search_payload(multiline, page),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _location_from_column(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""

    try:
        values = json.loads(value)
        if isinstance(values, list) and values:
            value = values[0]
    except (TypeError, ValueError):
        pass

    parts = [part for part in re.split(r"[-/]", value) if part]
    if len(parts) >= 3 and parts[0].upper() == "USA":
        return f"{parts[-1]}, {parts[-2]}"
    return value


def _state_abbreviation(state: str) -> str:
    states = {
        "Illinois": "IL",
    }
    return states.get(state, state)


def _parse_jobs_from_api(session: requests.Session, base_url: str, html: str, agency: dict) -> list[dict]:
    portal = _portal_number(html)
    if not portal:
        return []

    api_url = _search_api_url(base_url, portal)
    salary_payload = _post_search(session, api_url, multiline=False, page=1)
    detail_payload = _post_search(session, api_url, multiline=True, page=1)
    detail_by_id = {
        clean_text(item.get("jobId")): item
        for item in detail_payload.get("requisitionList", [])
    }

    jobs = []
    seen_urls = set()
    for item in salary_payload.get("requisitionList", []):
        job_id = clean_text(item.get("jobId"))
        contest_no = clean_text(item.get("contestNo"))
        columns = item.get("column") or []
        title = clean_text(columns[0] if len(columns) > 0 else "")
        salary_text = clean_text(columns[1] if len(columns) > 1 else "")
        if not title or not job_id:
            continue

        detail = detail_by_id.get(job_id, {})
        detail_columns = detail.get("column") or []
        employment_type = clean_text(detail_columns[1] if len(detail_columns) > 1 else "")
        location = _location_from_column(detail_columns[2] if len(detail_columns) > 2 else "")
        city = agency["city"]
        state = agency["state"]
        if "," in location:
            parts = [part.strip() for part in location.split(",") if part.strip()]
            city = parts[0] or city
            state = _state_abbreviation(parts[-1] or state)

        source_url = _detail_url(base_url, job_id)
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        raw_context = clean_text(" ".join([title, contest_no, salary_text, employment_type, location]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=salary_text,
                raw_context=raw_context,
                extra_fields={
                    "requisition_id": contest_no,
                    "employment_type": employment_type,
                },
            )
        )

    return jobs


def _looks_like_detail_url(url: str) -> bool:
    return "jobdetail.ftl" in url or re.search(r"[?&]job=\d+", url)


def _looks_like_title(title: str) -> bool:
    title = clean_text(title)
    lower = title.lower()
    return 4 <= len(title) <= 160 and lower not in BAD_TITLES and "sign in" not in lower


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:?\s*(.+?)(?=\s+[A-Z][A-Za-z ]+\s*:|$)", text)
    return clean_text(match.group(1)) if match else ""


def _parse_jobs_from_html(html: str, base_url: str, agency: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        source_url = urljoin(base_url, link["href"])
        if not _looks_like_detail_url(source_url):
            continue

        title = clean_text(link.get_text(" ", strip=True))
        container = link.find_parent(["tr", "li", "div"])
        raw_context = clean_text(container.get_text(" ", strip=True)) if container else title

        if not _looks_like_title(title):
            title = _extract_field(raw_context, "Position Title") or _extract_field(raw_context, "Requisition Title")
        if not _looks_like_title(title) or source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        location = _extract_field(raw_context, "Work Locations") or _extract_field(raw_context, "Location")
        city = location.split(",")[0].strip() if location else agency["city"]
        posted_date = _extract_field(raw_context, "Job Posting") or _extract_field(raw_context, "Posting Date")
        closing_date = _extract_field(raw_context, "Posting Expiration Date") or _extract_field(raw_context, "Unposting Date")
        req_id = _extract_field(raw_context, "Requisition ID")

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city or agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                posted_date=posted_date,
                closing_date=closing_date,
                raw_context=raw_context,
                extra_fields={"requisition_id": req_id},
            )
        )

    return jobs


def scrape_taleo(agency: dict) -> list[dict]:
    session = requests.Session()
    jobs = []
    seen_ids = set()

    for url in _candidate_urls(agency["jobs_url"]):
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        api_jobs = _parse_jobs_from_api(session, url, response.text, agency)
        if api_jobs:
            return api_jobs

        for job in _parse_jobs_from_html(response.text, url, agency):
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])
            jobs.append(job)

        if jobs:
            break

    return jobs
