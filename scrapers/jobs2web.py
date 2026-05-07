from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

MAX_PAGES = 20


def _search_url(base_url: str, page: int) -> str:
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    query.setdefault("q", [""])
    query.setdefault("sortColumn", ["sort_title"])
    query.setdefault("sortDirection", ["asc"])
    if page > 1:
        query["startrow"] = [str((page - 1) * 25)]
    encoded = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/search/", parsed.params, encoded, parsed.fragment))


def _detail_text(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    main = soup.select_one(".jobDisplay, .job, main, body")
    return clean_text((main or soup).get_text(" ", strip=True))


def _field_from_context(text: str, label: str) -> str:
    labels = "Location|Job Function|Date|Req ID|Salary|Employment Type|Department"
    import re

    match = re.search(
        rf"\b{label}\s*:?\s*(.+?)(?=\s+(?:{labels})\s*:?\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    return clean_text(match.group(1)) if match else ""


def scrape_jobs2web(agency: dict) -> list[dict]:
    session = requests.Session()
    jobs = []
    seen_urls = set()
    listing_base = agency["jobs_url"]

    for page in range(1, MAX_PAGES + 1):
        response = session.get(_search_url(listing_base, page), headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        links = soup.select("a.jobTitle-link[href]")
        if not links:
            break

        new_jobs = 0
        for link in links:
            title = clean_text(link.get_text(" ", strip=True))
            source_url = urljoin(listing_base, link["href"])
            if not title or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            new_jobs += 1

            row = link.find_parent("tr") or link.find_parent(class_="job-row") or link.find_parent()
            raw_context = clean_text(row.get_text(" ", strip=True)) if row else title
            detail_text = _detail_text(session, source_url)
            combined = clean_text(" ".join([raw_context, detail_text]))
            location = _field_from_context(combined, "Location")
            city = location.split(",")[0].strip() if location else agency["city"]
            state = agency["state"]

            jobs.append(
                normalize_job(
                    title=title,
                    agency=agency["agency"],
                    city=city or agency["city"],
                    state=state,
                    source_url=source_url,
                    platform=agency["platform"],
                    salary_text=extract_salary(combined),
                    posted_date=_field_from_context(combined, "Date"),
                    description=detail_text,
                    raw_context=combined,
                    extra_fields={
                        "requisition_id": _field_from_context(combined, "Req ID"),
                        "department": _field_from_context(combined, "Job Function"),
                    },
                )
            )

        if new_jobs == 0:
            break

    return jobs
