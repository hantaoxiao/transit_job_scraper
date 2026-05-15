import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import urlencode, urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

PAGE_SIZE = 50
MAX_PAGES = 20


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DETAIL_WORKERS = _env_int("UKG_DETAIL_WORKERS", 8)


def _parse_board_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    match = re.search(r"/([^/]+)/JobBoard/([^/?#]+)", parsed.path)
    if not match:
        raise ValueError(f"Cannot parse UKG job board URL: {url}")
    company_code, board_id = match.groups()
    return f"{parsed.scheme}://{parsed.netloc}", company_code, board_id


def _search_payload(skip: int) -> dict:
    return {
        "opportunitySearch": {
            "Top": PAGE_SIZE,
            "Skip": skip,
            "QueryString": "",
            "OrderBy": [
                {
                    "Value": "postedDateDesc",
                    "PropertyName": "PostedDate",
                    "Ascending": False,
                }
            ],
            "Filters": [
                {"t": "TermsSearchFilterDto", "fieldName": 4, "extra": None, "values": []},
                {"t": "TermsSearchFilterDto", "fieldName": 5, "extra": None, "values": []},
                {"t": "TermsSearchFilterDto", "fieldName": 6, "extra": None, "values": []},
            ],
        },
        "matchCriteria": {
            "PreferredJobs": [],
            "Educations": [],
            "LicenseAndCertifications": [],
            "Skills": [],
            "hasNoLicenses": False,
            "SkippedSkills": [],
        },
    }


def _detail_url(base: str, company_code: str, board_id: str, opportunity_id: str, posting_id: str = "") -> str:
    params = {"opportunityId": opportunity_id}
    if posting_id:
        params["postingId"] = posting_id
    return f"{base}/{company_code}/JobBoard/{board_id}/OpportunityDetail?{urlencode(params)}"


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def _money(value) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return clean_text(value)
    return f"${number:,.2f}"


def _salary_from_compensation(detail: dict) -> str:
    pay_range = detail.get("PayRange") if isinstance(detail.get("PayRange"), dict) else {}
    low = (
        detail.get("CompensationAnnualMinimum")
        or detail.get("CompensationHourlyMinimum")
        or pay_range.get("PayRangeMinimum")
    )
    high = (
        detail.get("CompensationAnnualMaximum")
        or detail.get("CompensationHourlyMaximum")
        or pay_range.get("PayRangeMaximum")
    )
    amount = detail.get("CompensationAmount")
    is_hourly = bool(detail.get("CompensationHourlyMinimum") or detail.get("CompensationHourlyMaximum"))

    if low and high:
        unit = " Hourly" if is_hourly else ""
        return clean_text(f"{_money(low)} - {_money(high)}{unit}")
    if amount:
        unit = " Hourly" if is_hourly else ""
        return clean_text(f"{_money(amount)}{unit}")
    return ""


def _decode_ukg_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def _detail_page_data(session: requests.Session, source_url: str) -> dict:
    try:
        response = session.get(source_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return {}

    html = response.text
    match = re.search(
        r"new\s+US\.Opportunity\.CandidateOpportunityDetail\((\{.*?\})\);",
        html,
        flags=re.DOTALL,
    )
    if not match:
        return {}

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def _location_from_ukg(value) -> str:
    if isinstance(value, list):
        locations = [_location_from_ukg(item) for item in value]
        return clean_text("; ".join(location for location in locations if location))

    if isinstance(value, dict):
        address = value.get("Address") or {}
        city = clean_text(address.get("City"))
        state = clean_text((address.get("State") or {}).get("Code") or address.get("State"))
        if city and state:
            return f"{city}, {state}"
        if city:
            return city

        description = clean_text(value.get("LocalizedDescription") or value.get("Description"))
        if " - " in description:
            return clean_text(description.split(" - ", 1)[1])
        return description

    return clean_text(value)


def scrape_ukg(agency: dict) -> list[dict]:
    base, company_code, board_id = _parse_board_url(agency["jobs_url"])
    search_url = f"{base}/{company_code}/JobBoard/{board_id}/JobBoardView/LoadSearchResults"
    session = requests.Session()
    opportunities_to_fetch = []
    seen_urls = set()

    for page in range(MAX_PAGES):
        skip = page * PAGE_SIZE
        response = session.post(search_url, headers=HEADERS, json=_search_payload(skip), timeout=30)
        response.raise_for_status()
        data = response.json()
        opportunities = data.get("opportunities", [])
        if not opportunities:
            break

        for item in opportunities:
            title = clean_text(item.get("Title"))
            opportunity_id = clean_text(item.get("Id") or item.get("OpportunityId"))
            posting_id = clean_text(item.get("PostingId"))
            if not title or not opportunity_id:
                continue

            source_url = _detail_url(base, company_code, board_id, opportunity_id, posting_id)
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)

            opportunities_to_fetch.append(
                {
                    "item": item,
                    "title": title,
                    "source_url": source_url,
                    "opportunity_id": opportunity_id,
                }
            )

        if len(opportunities) < PAGE_SIZE:
            break

    details = {}
    if opportunities_to_fetch:
        workers = min(DETAIL_WORKERS, len(opportunities_to_fetch))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_detail_page_data, requests.Session(), item["source_url"]): item
                for item in opportunities_to_fetch
            }
            for future in as_completed(futures):
                item = futures[future]
                details[item["source_url"]] = future.result()

    jobs = []
    for entry in opportunities_to_fetch:
        item = entry["item"]
        detail = details.get(entry["source_url"], {})
        location = _location_from_ukg(
            detail.get("Locations")
            or item.get("Location")
            or item.get("LocationName")
            or item.get("Locations")
            or item.get("City")
        )
        city = location.split(",")[0].strip() if location else agency["city"]
        description = _strip_html(detail.get("Description") or item.get("Description") or item.get("BriefDescription"))
        salary_text = _salary_from_compensation(detail) or extract_salary(description)
        posted_date = clean_text(detail.get("PostedDate") or item.get("PostedDate"))
        raw_context = clean_text(
            " ".join(
                str(value)
                for value in [
                    entry["title"],
                    item.get("RequisitionNumber"),
                    item.get("JobCategoryName"),
                    location,
                    posted_date,
                    salary_text,
                    description,
                ]
                if value
            )
        )

        jobs.append(
            normalize_job(
                title=entry["title"],
                agency=agency["agency"],
                city=city or agency["city"],
                state=agency["state"],
                source_url=entry["source_url"],
                platform=agency["platform"],
                salary_text=salary_text,
                posted_date=posted_date,
                category=clean_text(item.get("JobCategoryName")) or None,
                description=description,
                raw_context=raw_context,
                extra_fields={
                    "requisition_id": clean_text(item.get("RequisitionNumber")),
                    "opportunity_id": entry["opportunity_id"],
                },
            )
        )

    return jobs
