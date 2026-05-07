from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _detail_text(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    return clean_text(soup.get_text(" ", strip=True))


def scrape_jobvite(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()
    include_terms = [term.lower() for term in agency.get("include_terms", [])]

    for link in soup.select('a[href*="/job/"]'):
        title = clean_text(link.get_text(" ", strip=True))
        source_url = urljoin(agency["jobs_url"], link["href"])
        if not title or source_url in seen_urls:
            continue

        row = link.find_parent("tr") or link.find_parent("li") or link.find_parent()
        listing_context = clean_text(row.get_text(" ", strip=True)) if row else title
        if include_terms and not any(term in f"{title} {listing_context}".lower() for term in include_terms):
            continue

        seen_urls.add(source_url)
        detail_text = _detail_text(source_url)
        combined = clean_text(" ".join([title, listing_context, detail_text]))
        city = agency["city"]
        state = agency["state"]
        if "New York" in combined:
            city, state = "New York", "NY"
        if "Jersey City" in combined:
            city, state = "Jersey City", "NJ"

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                description=detail_text,
                raw_context=combined,
            )
        )

    return jobs
