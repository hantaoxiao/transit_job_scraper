import re
import time
from pathlib import Path
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

SEARCH_URL = "https://careers.mta.org/search/jobs"
HOME_URL = "https://careers.mta.org/"
MAX_PAGES = 20
BROWSER_PROFILE_DIR = Path(".mta_browser_profile")
JOB_LINK_SELECTOR = "a[href^='/jobs/'], a[href^='https://careers.mta.org/jobs/']"
DETAIL_READY_SELECTOR = "text=Description"
CLOUDFLARE_BLOCK_MARKERS = (
    "<title>Just a moment...</title>",
    "cf-browser-verification",
    "challenge-platform",
)
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
    "Work Location",
    "Hours of Work",
    "Salary Range",
    "Compression",
    "Metro-North Posting Date",
    "Metro-North Closing Date",
)


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*(.*?)(?=\s+[A-Z][A-Za-z ]+:\s*|$)", text)
    return clean_text(match.group(1)) if match else ""


def _extract_labeled_value(text: str, label: str) -> str:
    match = re.search(rf"(?im)^{re.escape(label)}:\s*(.+)$", text)
    return clean_text(match.group(1)) if match else ""


def _page_url(page: int) -> str:
    if page == 1:
        return SEARCH_URL
    return f"{SEARCH_URL}/in?page={page}"


def _is_cloudflare_blocked(html: str) -> bool:
    return any(marker in html for marker in CLOUDFLARE_BLOCK_MARKERS)


def _dedupe_jobs(jobs: list[dict]) -> list[dict]:
    deduped = []
    seen_ids = set()

    for job in jobs:
        if job["job_id"] in seen_ids:
            continue
        seen_ids.add(job["job_id"])
        deduped.append(job)

    return deduped


def _discover_search_urls(session: requests.Session) -> list[str]:
    """Discover MTA search pages from the homepage as a fallback.

    Some environments receive a 403 on /search/jobs. Category pages can
    still be reachable, so we crawl links from the homepage navigation.
    """
    response = session.get(HOME_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    urls = [SEARCH_URL]
    seen = {SEARCH_URL}

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not href.startswith("/search/") or not href.endswith("/jobs"):
            continue
        full_url = urljoin(HOME_URL, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        urls.append(full_url)

    return urls


def _discover_search_urls_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = [SEARCH_URL]
    seen = {SEARCH_URL}

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not href.startswith("/search/") or not href.endswith("/jobs"):
            continue
        full_url = urljoin(HOME_URL, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        urls.append(full_url)

    return urls


def _is_job_href(href: str) -> bool:
    return urlparse(href).path.startswith("/jobs/")


def _location_to_city_state(location: str, agency: dict) -> tuple[str, str]:
    city = agency["city"]
    state = agency["state"]

    if location:
        location = location.replace(", United States", "")
        city_state = [part.strip() for part in location.split(",") if part.strip()]
        if city_state:
            city = city_state[0]
        if len(city_state) > 1:
            state = city_state[1]

    return city, state


def _meaningful_lines_from_text(text: str) -> list[str]:
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    if "Back to job search" in lines:
        lines = lines[lines.index("Back to job search") + 1 :]
    if "Apply Now" in lines:
        lines = lines[: lines.index("Apply Now")]

    skipped = {
        "Skip to main content",
        "Careers",
        "All Jobs",
        "Jobs by Area",
        "Saved Jobs",
        "Benefits",
        "Diversity & Inclusion",
        "Veterans",
        "Events",
        "Application Status",
    }
    lines = [line for line in lines if line not in skipped]
    combined_lines = []
    labels = set(DETAIL_LABELS)
    i = 0

    while i < len(lines):
        line = lines[i]
        label = line.rstrip(":")
        inline_label = next((name for name in labels if line.startswith(f"{name}:")), "")

        if label in labels and line.endswith(":") and i + 1 < len(lines):
            combined_lines.append(f"{line} {lines[i + 1]}")
            i += 2
            continue

        if (label in labels or inline_label) and i + 1 < len(lines) and lines[i + 1].startswith("- "):
            combined_lines.append(f"{line} {lines[i + 1]}")
            i += 2
            continue

        combined_lines.append(line)
        i += 1

    return combined_lines


def _parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    lines = _meaningful_lines_from_text(text)
    meaningful_text = "\n".join(lines)

    details = {
        "all_meaningful_info": meaningful_text,
        "full_job_description": "",
        "mta_job_id": _extract_labeled_value(meaningful_text, "Job ID"),
        "business_unit": _extract_labeled_value(meaningful_text, "Business Unit"),
        "employment_type": _extract_labeled_value(meaningful_text, "Regular/Temporary"),
        "department": _extract_labeled_value(meaningful_text, "Department"),
        "authority": _extract_labeled_value(meaningful_text, "Authority"),
        "division_unit": _extract_labeled_value(meaningful_text, "Division/Unit"),
        "reports_to": _extract_labeled_value(meaningful_text, "Reports to"),
        "work_location": _extract_labeled_value(meaningful_text, "Work Location"),
        "hours_of_work": _extract_labeled_value(meaningful_text, "Hours of Work"),
    }

    location = _extract_labeled_value(meaningful_text, "Location")
    if location:
        details["detail_location"] = location

    posted_date = (
        _extract_labeled_value(meaningful_text, "Date Posted")
        or _extract_labeled_value(meaningful_text, "First Date of Posting")
        or _extract_labeled_value(meaningful_text, "Metro-North Posting Date")
    )
    if posted_date:
        details["posted_date"] = posted_date

    closing_date = _extract_labeled_value(meaningful_text, "Metro-North Closing Date")
    if closing_date:
        details["closing_date"] = closing_date

    salary_text = _extract_labeled_value(meaningful_text, "Salary Range")
    if salary_text:
        details["salary_text"] = salary_text

    if "Description" in lines:
        details["full_job_description"] = "\n".join(lines[lines.index("Description") + 1 :])

    for label in DETAIL_LABELS:
        value = _extract_labeled_value(meaningful_text, label)
        if value:
            key = "mta_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
            details[key] = value

    return details


def _build_mta_job(summary: dict, agency: dict, details: dict | None = None) -> dict:
    details = details or {}
    location = details.get("detail_location") or summary.get("location", "")
    city, state = _location_to_city_state(location, agency)

    all_info = details.get("all_meaningful_info") or summary.get("raw_context", "")
    department = details.get("department") or summary.get("department", "")
    description = details.get("full_job_description") or department

    return normalize_job(
        title=summary["title"],
        agency=agency["agency"],
        city=city,
        state=state,
        source_url=summary["source_url"],
        platform=agency["platform"],
        salary_text=details.get("salary_text"),
        posted_date=details.get("posted_date") or summary.get("posted_date", ""),
        closing_date=details.get("closing_date", ""),
        description=description,
        raw_context=all_info,
        extra_fields=details,
    )


def _parse_search_page(html: str, agency: dict, normalize: bool = True) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not _is_job_href(href):
            continue

        title = clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        source_url = urljoin(SEARCH_URL, href)
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        container = link.find_parent(["article", "li", "tr", "div"])
        raw_context = clean_text(container.get_text(" ", strip=True)) if container else title
        location = _extract_field(raw_context, "Location")
        posted_date = _extract_field(raw_context, "Date Posted")
        department = _extract_field(raw_context, "Department")

        summary = {
            "title": title,
            "source_url": source_url,
            "location": location,
            "posted_date": posted_date,
            "department": department,
            "raw_context": raw_context,
        }

        jobs.append(_build_mta_job(summary, agency) if normalize else summary)

    return jobs


def _scrape_mta_requests(agency: dict) -> list[dict]:
    jobs = []
    session = requests.Session()
    search_urls = _discover_search_urls(session)

    for search_url in search_urls:
        for page in range(1, MAX_PAGES + 1):
            page_url = search_url if page == 1 else f"{search_url}/in?page={page}"
            try:
                response = session.get(page_url, headers=HEADERS, timeout=30)
                response.raise_for_status()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 403:
                    if page == 1:
                        break
                    return jobs
                raise

            if _is_cloudflare_blocked(response.text):
                raise requests.HTTPError("Cloudflare challenge page returned", response=response)

            page_jobs = _parse_search_page(response.text, agency)
            if not page_jobs:
                break

            jobs.extend(page_jobs)

            time.sleep(0.5)

    return _dedupe_jobs(jobs)


def _wait_for_mta_browser_page(page, url: str, selector: str | None = None) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)

    if selector:
        try:
            page.wait_for_selector(selector, timeout=15_000)
        except Exception:
            pass

    html = page.content()
    if _is_cloudflare_blocked(html):
        print("MTA returned a browser challenge. Complete it in the opened browser window.")
        wait_selector = selector or "body"
        page.wait_for_selector(wait_selector, timeout=120_000)
        html = page.content()

    return html


def _scrape_mta_browser(agency: dict) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "MTA blocked requests. Install the browser fallback with: "
            "pip install playwright && playwright install chromium"
        ) from exc

    summaries = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()

        _wait_for_mta_browser_page(page, HOME_URL, "a[href^='/search/']")
        search_urls = [SEARCH_URL]

        for search_url in search_urls:
            for page_num in range(1, MAX_PAGES + 1):
                page_url = search_url if page_num == 1 else f"{search_url}/in?page={page_num}"
                html = _wait_for_mta_browser_page(page, page_url, JOB_LINK_SELECTOR)
                page_summaries = _parse_search_page(html, agency, normalize=False)
                if not page_summaries:
                    break

                summaries.extend(page_summaries)
                time.sleep(0.5)

        summaries = _dedupe_jobs([_build_mta_job(summary, agency) for summary in summaries])
        summary_by_url = {job["source_url"]: job for job in summaries}
        jobs = []

        for index, source_url in enumerate(summary_by_url, start=1):
            if index == 1 or index % 25 == 0:
                print(f"Enriching MTA job details {index}/{len(summary_by_url)}")

            detail_html = _wait_for_mta_browser_page(page, source_url, DETAIL_READY_SELECTOR)
            details = _parse_detail_page(detail_html)
            summary = {
                "title": summary_by_url[source_url]["title"],
                "source_url": source_url,
                "location": summary_by_url[source_url]["raw_context"],
                "posted_date": summary_by_url[source_url]["posted_date"],
                "department": summary_by_url[source_url]["description"],
                "raw_context": summary_by_url[source_url]["raw_context"],
            }
            jobs.append(_build_mta_job(summary, agency, details))
            time.sleep(0.2)

        context.close()

    return _dedupe_jobs(jobs)


def scrape_mta(agency: dict) -> list[dict]:
    try:
        return _scrape_mta_requests(agency)
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if response is None or response.status_code != 403:
            raise

        print("MTA blocked the requests scraper; trying local browser fallback.")
        return _scrape_mta_browser(agency)
