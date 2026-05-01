import re
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

DEFAULT_LISTING_PATH = "/go/View-All-Jobs/8606400/"


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s+(.+?)(?=\s+(?:Req ID|City|Facility|Department|Title)\s+|$)", text)
    return clean_text(match.group(1)) if match else ""


def scrape_successfactors(agency: dict) -> list[dict]:
    url = urljoin(agency["jobs_url"], DEFAULT_LISTING_PATH)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.select("a.jobTitle-link[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        source_url = urljoin(url, link["href"])
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        row = link.find_parent(class_="job-row") or link.find_parent()
        raw_context = clean_text(row.get_text(" ", strip=True)) if row else title
        city = _extract_field(raw_context, "City") or agency["city"]
        department = _extract_field(raw_context, "Department")

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                description=department,
                raw_context=raw_context,
            )
        )

    return jobs
