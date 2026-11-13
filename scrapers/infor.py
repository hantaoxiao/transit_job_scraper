"""Public Infor Landmark Candidate Self-Service job listings and details."""

from datetime import datetime
import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
PAGE_SIZE = 100
MAX_PAGES = 30
RESOURCE_PATTERN = re.compile(r"JobPosting\[JobPostingSet\]\(\d+,\d+,\d+\)")


def _load_url(url: str, *, listing: bool = False) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.pop("output", None)
    params.pop("menu", None)
    params.update(pageop="load", pagesize=str(PAGE_SIZE if listing else 1))
    return parsed._replace(query=urlencode(params), fragment="").geturl()


def _json(session: requests.Session, url: str) -> dict:
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Infor returned a non-JSON response for {url}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "COMPLETED":
        raise RuntimeError(f"Infor did not complete the public job request for {url}")
    return payload


def _field(view: dict, name: str) -> str:
    field = view.get("fields", {}).get(name, {})
    return clean_text(field.get("value")) if isinstance(field, dict) else ""


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def _listings(session: requests.Session, agency: dict) -> list[dict]:
    url = _load_url(agency["jobs_url"], listing=True)
    allowed = urlparse(url)
    records = {}
    seen_pages = set()
    for _ in range(MAX_PAGES):
        if url in seen_pages:
            raise RuntimeError("Infor job listing repeated a pagination URL")
        seen_pages.add(url)
        payload = _json(session, url)
        views = payload.get("dataViewSet")
        if not isinstance(views, dict) or not isinstance(views.get("data"), list):
            raise RuntimeError("Infor job listing has an unrecognized dataViewSet")
        previous_count = len(records)
        for record in views["data"]:
            resource = record.get("resourceId", "")
            if not RESOURCE_PATTERN.fullmatch(resource) or not _field(record, "Description"):
                raise RuntimeError("Infor job listing contains an unrecognized posting")
            records.setdefault(resource, record)
        paging = views.get("pagingInfo", {})
        if paging.get("hasNext") is False:
            return list(records.values())
        if paging.get("hasNext") is not True:
            raise RuntimeError("Infor job listing has no recognized pagination status")
        if len(records) == previous_count:
            raise RuntimeError("Infor pagination returned no new postings before the last page")
        next_link = views.get("pagingUrls", {}).get("nextPageUrl")
        if not next_link:
            raise RuntimeError("Infor job listing is missing its next-page URL")
        next_url = urlparse(urljoin(url, next_link))
        if (next_url.scheme, next_url.netloc, next_url.path) != (allowed.scheme, allowed.netloc, allowed.path):
            raise RuntimeError("Infor next-page URL points outside the configured public job list")
        url = next_url._replace(fragment="").geturl()
    raise RuntimeError(f"Infor job listing exceeded {MAX_PAGES} pages")


def _public_job_url(board_url: str, resource: str) -> str:
    if not RESOURCE_PATTERN.fullmatch(resource):
        raise ValueError("Invalid Infor job posting resource")
    parsed = urlparse(board_url)
    base_path, list_name = parsed.path.rsplit("/list/", 1)
    context = {key: value for key, value in parse_qsl(parsed.query) if key.startswith("csk.")}
    context.update(fromlist=unquote(list_name), navigation=resource + ".JobPostingDisplayNav")
    path = base_path + "/form/" + quote(resource + ".JobPostingDisplay", safe="")
    return parsed._replace(path=path, query=urlencode(context), fragment="").geturl()


def _description_and_salary(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    description = clean_text(soup.get_text(" ", strip=True))
    for node in soup.find_all(["p", "li"]):
        text = clean_text(node.get_text(" ", strip=True))
        if "$" in text and re.search(r"\b(salar(?:y|ies)|pay|compensation)\b", text, re.I):
            salary = extract_salary(text)
            if salary:
                return description, salary
    return description, extract_salary(description)


def _job(record: dict, detail: dict, agency: dict, source_url: str) -> dict:
    html = _field(detail, "_op_PositionDescription_spc_translation_cp_")
    if not html:
        raise RuntimeError(f"Infor job description is missing for {record['resourceId']}")
    description, salary = _description_and_salary(html)
    title = _field(detail, "_op_Description_spc_translation_cp_") or _field(record, "Description")
    city = _field(record, "LocationOfJob_prd_Location_ohb_3_chb_") or agency["city"]
    state = _field(record, "LocationOfJob_prd_Location_ohb_2_chb_") or agency["state"]
    department = _field(record, "CategoryDescriptionForSort") or _field(record, "Category")
    work_type = {"FT": "Full Time", "PT": "Part Time"}.get(_field(record, "WorkType"), _field(record, "WorkType"))
    posted = _date(_field(record, "PostingDateRange_prd_Begin"))
    closing = _date(_field(detail, "PostingDateRange_prd_End"))
    context = clean_text(" ".join([title, city, state, department, work_type, salary, description]))
    return normalize_job(
        title=title, agency=agency["agency"], city=city, state=state,
        source_url=source_url, platform=agency["platform"], salary_text=salary,
        description=description, raw_context=context, posted_date=posted, closing_date=closing,
        extra_fields={
            "requisition_id": _field(record, "JobRequisition") or _field(record, "JobId"),
            "department": department, "employment_type": work_type,
            "infor_resource_id": record["resourceId"],
        },
    )


def scrape_infor(agency: dict) -> list[dict]:
    with requests.Session() as session:
        records = _listings(session, agency)
        jobs = []
        for record in records:
            source_url = _public_job_url(agency["jobs_url"], record["resourceId"])
            detail = _json(session, _load_url(source_url))
            if detail.get("resourceId") != record["resourceId"] or not isinstance(detail.get("fields"), dict):
                raise RuntimeError("Infor returned a different or unrecognized job detail")
            jobs.append(_job(record, detail, agency, source_url))
        return jobs
