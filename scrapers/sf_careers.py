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


def _label_value(text: str, label: str) -> str:
    labels = (
        "Recruitment",
        "Published",
        "Contact",
        "Department",
        "Job class",
        "Salary range",
        "Role type",
        "Hours",
        "Exam type",
        "Rule",
        "List type",
        "About",
        "Application Opening",
        "Application Deadline",
        "Annual Salary",
        "Appointment Type",
        "Division",
        "Section/Unit",
        "Work Location",
        "Work Hours",
        "Role description",
    )
    lookahead = "|".join(item for item in labels if item != label)
    marker = f"{label}:"
    start = text.find(marker)
    if start == -1:
        return ""
    start += len(marker)

    end = len(text)
    for next_label in lookahead.split("|"):
        idx = text.find(f"{next_label}:", start)
        if idx != -1:
            end = min(end, idx)

    return clean_text(text[start:end])


def _role_detail(session: requests.Session, url: str) -> dict:
    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return {}

    soup = BeautifulSoup(response.text, "lxml")
    text = clean_text(soup.get_text(" ", strip=True))
    return {
        "salary_text": _label_value(text, "Salary range"),
        "posted_date": _label_value(text, "Published"),
        "closing_date": _label_value(text, "Application Deadline"),
        "department": _label_value(text, "Department"),
        "employment_type": _label_value(text, "Role type"),
        "requisition_id": _label_value(text, "Recruitment"),
        "description": text,
    }


def scrape_sf_careers(agency: dict) -> list[dict]:
    session = requests.Session()
    response = session.post(
        agency["jobs_url"],
        headers=HEADERS,
        data={"offset": "0", "q": "", "department": agency.get("department_id", "")},
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()

    for item in soup.select(".listJob [itemscope]"):
        link = item.select_one('a[itemprop="url"][href]')
        title_el = item.select_one('[itemprop="title"]')
        if not link or not title_el:
            continue

        title = clean_text(title_el.get_text(" ", strip=True))
        source_url = urljoin(agency["jobs_url"], link["href"])
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        context = clean_text(item.get_text(" ", strip=True))
        detail = _role_detail(session, source_url)
        description = detail.get("description", "")

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=detail.get("salary_text", ""),
                posted_date=detail.get("posted_date", ""),
                closing_date=detail.get("closing_date", ""),
                description=description,
                raw_context=clean_text(" ".join([context, description])),
                extra_fields={
                    "requisition_id": detail.get("requisition_id", ""),
                    "employment_type": detail.get("employment_type", ""),
                    "department": detail.get("department", ""),
                },
            )
        )

    return jobs
