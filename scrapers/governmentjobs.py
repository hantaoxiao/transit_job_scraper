import time
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


BAD_LINK_TEXT = {
    "sign in",
    "menu",
    "privacy",
    "terms",
    "job alerts",
    "powered by",
    "accessibility",
    "profile",
    "help",
    "home",
    "contact",
    "share",
    "print",
}


def looks_like_link_text(title: str) -> bool:
    title = clean_text(title)
    title_lower = title.lower()

    if len(title) < 5 or len(title) > 140:
        return False

    if title_lower in BAD_LINK_TEXT:
        return False

    return True


def looks_like_job_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return "/careers/" in path and "/jobs/" in path


def scrape_governmentjobs(agency: dict) -> list[dict]:
    """
    Starter scraper for GovernmentJobs / NEOGOV career pages.

    This is intentionally conservative. It grabs likely job links and normalizes them.
    If GovernmentJobs changes its page structure, update selectors here once and all
    GovernmentJobs agencies benefit.
    """
    url = agency["jobs_url"]
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    jobs = []

    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))
        href = link["href"]
        full_url = urljoin(url, href)

        if not looks_like_link_text(title):
            continue

        if not looks_like_job_detail_url(full_url):
            continue

        parent = link.find_parent()
        raw_context = clean_text(parent.get_text(" ", strip=True)) if parent else title

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=full_url,
                platform=agency["platform"],
                raw_context=raw_context,
            )
        )

    # Give a polite delay if this function is reused in loops.
    time.sleep(1)
    return jobs
