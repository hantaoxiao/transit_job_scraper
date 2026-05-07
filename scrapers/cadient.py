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


def _detail_text(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    return clean_text(soup.get_text(" ", strip=True))


def scrape_cadient(agency: dict) -> list[dict]:
    session = requests.Session()
    response = session.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.select('a[href*="SEQ=jobDetails"], a[href*="seq=jobDetails"]'):
        title = clean_text(link.get_text(" ", strip=True))
        source_url = urljoin(agency["jobs_url"], link["href"])
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        row = link.find_parent("tr") or link.find_parent()
        listing_context = clean_text(row.get_text(" ", strip=True)) if row else title
        detail_text = _detail_text(session, source_url)
        combined = clean_text(" ".join([title, listing_context, detail_text]))

        city = agency["city"]
        state = agency["state"]
        if "Chicago" in combined:
            city, state = "Chicago", "IL"

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
