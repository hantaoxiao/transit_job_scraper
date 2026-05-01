import re
import time
from urllib.parse import urljoin

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
MAX_PAGES = 20


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*(.*?)(?=\s+[A-Z][A-Za-z ]+:\s*|$)", text)
    return clean_text(match.group(1)) if match else ""


def _page_url(page: int) -> str:
    if page == 1:
        return SEARCH_URL
    return f"{SEARCH_URL}/in?page={page}"


def _parse_search_page(html: str, agency: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("/jobs/"):
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

        city = agency["city"]
        state = agency["state"]
        if location:
            city_state = [part.strip() for part in location.split(",") if part.strip()]
            if city_state:
                city = city_state[0]
            if len(city_state) > 1:
                state = city_state[1]

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                posted_date=posted_date,
                description=department,
                raw_context=raw_context,
            )
        )

    return jobs


def scrape_mta(agency: dict) -> list[dict]:
    jobs = []
    seen_ids = set()

    for page in range(1, MAX_PAGES + 1):
        response = requests.get(_page_url(page), headers=HEADERS, timeout=30)
        response.raise_for_status()

        page_jobs = _parse_search_page(response.text, agency)
        if not page_jobs:
            break

        for job in page_jobs:
            if job["job_id"] in seen_ids:
                continue
            seen_ids.add(job["job_id"])
            jobs.append(job)

        time.sleep(0.5)

    return jobs
