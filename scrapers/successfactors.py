import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job
from scrapers.detail_cache import cached_detail_text, cached_job, has_cached_detail


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

DEFAULT_LISTING_PATH = "/go/View-All-Jobs/8606400/"


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DETAIL_WORKERS = _env_int("SUCCESSFACTORS_DETAIL_WORKERS", 8)


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s+(.+?)(?=\s+(?:Req ID|City|Facility|Department|Title)\s+|$)", text)
    return clean_text(match.group(1)) if match else ""


def _detail_text(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "lxml")
    return clean_text(soup.get_text(" ", strip=True))


def scrape_successfactors(agency: dict) -> list[dict]:
    url = urljoin(agency["jobs_url"], DEFAULT_LISTING_PATH)
    session = requests.Session()
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    entries = []
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
        cached = cached_job(agency["agency"], source_url=source_url, title=title)
        entries.append(
            {
                "title": title,
                "source_url": source_url,
                "raw_context": raw_context,
                "city": city,
                "department": department,
                "cached": cached,
            }
        )

    details = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_detail_text, requests.Session(), entry["source_url"]): entry
                for entry in pending
            }
            for future in as_completed(futures):
                entry = futures[future]
                details[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        cached = entry["cached"]
        live_detail = details.get(entry["source_url"])
        detail_text = live_detail or cached_detail_text(cached)
        combined_context = clean_text(
            " ".join(value for value in [entry["raw_context"], live_detail or cached.get("salary_text", "")] if value)
        )
        salary_text = extract_salary(detail_text) if live_detail else cached.get("salary_text", "")

        jobs.append(
            normalize_job(
                title=entry["title"],
                agency=agency["agency"],
                city=entry["city"],
                state=agency["state"],
                source_url=entry["source_url"],
                platform=agency["platform"],
                salary_text=salary_text or cached.get("salary_text", ""),
                description=detail_text or entry["department"],
                raw_context=combined_context,
            )
        )

    return jobs
