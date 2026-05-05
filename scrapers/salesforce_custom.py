import re
from urllib.parse import urljoin, urlparse
from urllib.parse import parse_qs

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

NJ_TRANSIT_LIST_PAGES = (
    "/CorporateListPage?jobsite=Default&p=Candidate&page=CorporateListPage",
    "/JobListPage1Custom?jobsite=default&p=Candidate&page=BusJobListPage",
    "/JobListPage1Custom?jobsite=default&p=Candidate&page=RailJobListPage",
)

BAD_TITLES = {
    "search",
    "apply",
    "view",
    "login",
    "register",
    "forgot password",
    "job title",
    "keywords",
    "keywords:",
    "return to list",
    "new user",
}


def _base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _candidate_urls(url: str) -> list[str]:
    base = _base_url(url)
    parsed = urlparse(url)
    urls = [] if parsed.path in {"", "/"} else [url]
    urls.extend(urljoin(base, page) for page in NJ_TRANSIT_LIST_PAGES)
    deduped = []
    seen = set()
    for candidate in urls:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _looks_like_title(title: str) -> bool:
    title = clean_text(title)
    lower = title.lower()
    if len(title) < 4 or len(title) > 160:
        return False
    if lower in BAD_TITLES:
        return False
    return not any(noise in lower for noise in ["welcome to", "important information", "career portal"])


def _looks_like_job_url(url: str) -> bool:
    lower = url.lower()
    return any(token in lower for token in ["jobdetail", "jobid=", "jobids=", "job_id=", "postingid=", "posting_id="])


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:?\s*(.+?)(?=\s+[A-Z][A-Za-z /&]+\s*:|$)", text)
    return clean_text(match.group(1)) if match else ""


def _detail_page_text(session: requests.Session, source_url: str) -> str:
    def useful(text: str) -> bool:
        return bool(re.search(r"\b(Job Details|Salary Range|Starting pay rate|top pay rate)\b", text, flags=re.IGNORECASE))

    def page_text(url: str) -> str:
        try:
            response = session.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            return ""
        return clean_text(BeautifulSoup(response.text, "lxml").get_text(" ", strip=True))

    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)
    page = (query.get("page") or [""])[0]
    job_ids = (query.get("jobIds") or query.get("JobIds") or [""])[0]
    if page and job_ids:
        iframe_query = parsed.query.replace("jobIds=", "JobIds=")
        iframe_url = urljoin(source_url, f"{page}1?{iframe_query}")
        iframe_text = page_text(iframe_url)
        if useful(iframe_text):
            return iframe_text

        direct_url = urljoin(source_url, f"{page}?{iframe_query}")
        direct_text = page_text(direct_url)
        if useful(direct_text):
            return direct_text

    try:
        response = session.get(source_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "lxml")
    iframe = soup.find("iframe", src=True)
    if iframe:
        iframe_url = urljoin(source_url, iframe["src"])
        iframe_text = page_text(iframe_url)
        if iframe_text:
            return iframe_text

    return clean_text(soup.get_text(" ", strip=True))


def _job_from_summary(summary: dict, agency: dict, detail_text: str = "") -> dict:
    context = clean_text(" ".join(value for value in [summary.get("raw_context", ""), detail_text] if value))
    location_match = re.search(r"Job Location City:\s*(.*?)\s+State:\s*([A-Z]{2})\b", detail_text)
    location = clean_text(location_match.group(1)) if location_match else _extract_field(context, "Location")
    location = re.sub(r"^s:\s*", "", location, flags=re.IGNORECASE)
    state = clean_text(location_match.group(2)) if location_match else agency["state"]
    city = location.split(",")[0].strip() if location else summary.get("city") or agency["city"]
    salary_text = extract_salary(detail_text or context)

    return normalize_job(
        title=summary["title"],
        agency=agency["agency"],
        city=city or agency["city"],
        state=state or agency["state"],
        source_url=summary["source_url"],
        platform=agency["platform"],
        salary_text=salary_text,
        raw_context=context or summary["title"],
        extra_fields={"requisition_id": summary.get("requisition_id", "")},
    )


def _parse_link_jobs(soup: BeautifulSoup, page_url: str, agency: dict) -> list[dict]:
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        source_url = urljoin(page_url, link["href"])
        title = clean_text(link.get_text(" ", strip=True))
        if not _looks_like_job_url(source_url) or not _looks_like_title(title):
            continue
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        container = link.find_parent(["tr", "li", "div"])
        raw_context = clean_text(container.get_text(" ", strip=True)) if container else title
        location = _extract_field(raw_context, "Location")
        city = location.split(",")[0].strip() if location else agency["city"]

        jobs.append(
            {
                "title": title,
                "city": city or agency["city"],
                "source_url": source_url,
                "raw_context": raw_context,
                "requisition_id": _extract_field(raw_context, "Job ID"),
            }
        )

    return jobs


def _parse_table_jobs(soup: BeautifulSoup, page_url: str, agency: dict) -> list[dict]:
    jobs = []
    for row in soup.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue

        link = row.find("a", href=True)
        source_url = urljoin(page_url, link["href"]) if link else page_url
        title = clean_text(link.get_text(" ", strip=True)) if link else cells[0]
        if not link or not _looks_like_job_url(source_url) or not _looks_like_title(title):
            continue

        raw_context = clean_text(" ".join(cells))
        location = next((cell for cell in cells if re.search(r"\bNJ\b|New Jersey|Newark|Maplewood|Camden", cell)), "")
        city = location.split(",")[0].strip() if location else agency["city"]

        jobs.append(
            {
                "title": title,
                "city": city or agency["city"],
                "source_url": source_url,
                "raw_context": raw_context,
                "requisition_id": _extract_field(raw_context, "Job ID"),
            }
        )

    return jobs


def scrape_salesforce_custom(agency: dict) -> list[dict]:
    session = requests.Session()
    jobs = []
    seen_ids = set()

    for url in _candidate_urls(agency["jobs_url"]):
        try:
            response = session.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403, 404}:
                continue
            raise
        soup = BeautifulSoup(response.text, "lxml")

        page_jobs = _parse_link_jobs(soup, url, agency)
        if not page_jobs:
            page_jobs = _parse_table_jobs(soup, url, agency)

        for summary in page_jobs:
            detail_text = _detail_page_text(session, summary["source_url"])
            job = _job_from_summary(summary, agency, detail_text)
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])
            jobs.append(job)

    return jobs
