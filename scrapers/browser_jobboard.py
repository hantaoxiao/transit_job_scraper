import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError, sync_playwright

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


def _render_page(url: str, wait_ms: int = 8000) -> tuple[str, list[tuple[str, str]]]:
    body_text = ""
    links = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(wait_ms)
            body_text = page.locator("body").inner_text(timeout=5000)
            for index in range(min(page.locator("a").count(), 500)):
                link = page.locator("a").nth(index)
                text = clean_text(link.inner_text(timeout=500))
                href = link.get_attribute("href") or ""
                if text or href:
                    links.append((text, urljoin(url, href)))
            browser.close()
    except PlaywrightError:
        return "", []
    return body_text, links


def _city_state_from_location(location: str, agency: dict) -> tuple[str, str]:
    parts = [part.strip() for part in clean_text(location).split(",") if part.strip()]
    if len(parts) >= 2:
        state = parts[-1].split()[0]
        if re.fullmatch(r"[A-Z]{2}", state):
            return parts[-2], state
    return agency["city"], agency["state"]


def scrape_adp(agency: dict) -> list[dict]:
    body_text, _ = _render_page(agency["jobs_url"], wait_ms=10000)
    match = re.search(
        r"Current Openings\s+\(\d+\s+of\s+\d+\)\s+Search\s+(.+?)\s+Stay connected with us",
        body_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return _scrape_adp_myjobs(agency, body_text)

    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    jobs = []
    index = 0
    while index + 1 < len(lines):
        title = clean_text(lines[index])
        location = clean_text(lines[index + 1])
        meta = clean_text(lines[index + 2]) if index + 2 < len(lines) else ""

        if not title or title.lower() in {"search", "actions"}:
            index += 1
            continue

        city, state = _city_state_from_location(location, agency)
        posted_date = ""
        employment_type = ""
        posted_match = re.search(r"(\bToday\b|\b\d+\s+days?\s+ago\b|\b30\+\s+days?\s+ago\b)", meta, flags=re.IGNORECASE)
        if posted_match:
            posted_date = posted_match.group(1)
            employment_type = clean_text(meta[posted_match.end() :])
        else:
            employment_type = meta

        raw_context = clean_text(" ".join([title, location, meta]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=agency["jobs_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                posted_date=posted_date,
                raw_context=raw_context,
                extra_fields={"employment_type": employment_type},
            )
        )
        index += 3

    return jobs


def _scrape_adp_myjobs(agency: dict, body_text: str) -> list[dict]:
    match = re.search(r"Recently Posted Jobs\s+(.+?)\s+Show all", body_text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    chunks = re.split(r"\nApply\n", match.group(1))
    jobs = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        title = clean_text(lines[0])
        location = clean_text(lines[1])
        requisition_id = clean_text(lines[2])
        description = clean_text(" ".join(lines[3:]))
        if not title or title.lower() in {"create job alert"}:
            continue
        city, state = _city_state_from_location(location, agency)
        raw_context = clean_text(" ".join([title, location, requisition_id, description]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=agency["jobs_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                description=description,
                raw_context=raw_context,
                extra_fields={"requisition_id": requisition_id},
            )
        )
    return jobs


def scrape_dayforce(agency: dict) -> list[dict]:
    _, links = _render_page(agency["jobs_url"], wait_ms=10000)
    jobs = []
    seen_urls = set()

    for title, source_url in links:
        if not title or title.lower() == "read more" or "/jobs/" not in source_url:
            continue
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        detail_text = _detail_text(source_url)
        location = ""
        location_match = re.search(r"\b([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})\b", detail_text)
        if location_match:
            location = location_match.group(1)
        city, state = _city_state_from_location(location, agency)
        raw_context = clean_text(" ".join([title, detail_text]))

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                description=detail_text,
                raw_context=raw_context,
            )
        )

    return jobs


def scrape_applicantpro(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=8000)
    jobs = []
    seen_urls = set()
    job_links = [(title, url) for title, url in links if re.search(r"/jobs/\d+", url)]

    for title, source_url in job_links:
        title = clean_text(title)
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        detail_text = _detail_text(source_url)
        context_match = re.search(
            rf"{re.escape(title)}\s+(.+?)(?=\n[A-Z][^\n]+\n|Sign Up For Job Alerts|$)",
            body_text,
            flags=re.DOTALL,
        )
        listing_context = clean_text(context_match.group(1)) if context_match else ""
        combined = clean_text(" ".join([title, listing_context, detail_text]))
        location_match = re.search(r"([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})", combined)
        city, state = _city_state_from_location(location_match.group(1) if location_match else "", agency)

        posted = ""
        posted_match = re.search(r"\bPosted:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", listing_context)
        if posted_match:
            posted = posted_match.group(1)
        closing = ""
        closing_match = re.search(r"\bClosing Date:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", listing_context)
        if closing_match:
            closing = closing_match.group(1)

        employment_type = ""
        if re.search(r"\bPart Time\b|\bPart-Time\b", listing_context, flags=re.IGNORECASE):
            employment_type = "Part-time"
        elif re.search(r"\bFull Time\b|\bFull-Time\b", listing_context, flags=re.IGNORECASE):
            employment_type = "Full-time"

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                posted_date=posted,
                closing_date=closing,
                description=detail_text,
                raw_context=combined,
                extra_fields={"employment_type": employment_type},
            )
        )

    return jobs


def scrape_static_job_links(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=7000)
    jobs = []
    seen_urls = set()

    for title, source_url in links:
        title = clean_text(title)
        if not title or source_url in seen_urls:
            continue
        blob = f"{title} {source_url}".lower()
        if not re.search(r"(/jobs/\d+|gnk=job|jobid=|positiondetails|candidateexperience/.+/job/|/job/)", source_url, re.I):
            continue
        if title.lower() in {
            "jobs",
            "careers",
            "apply",
            "apply here",
            "click here",
            "view job",
            "read more",
            "skip to main content",
            "find jobs",
            "search jobs",
            "job type",
            "all positions",
            "career fairs",
            "hiring programs",
            "join our team",
            "current employees",
        }:
            continue
        if len(title) < 4 or len(title) > 120:
            continue
        if re.search(r"\b(home|privacy|legal|facebook|twitter|linkedin|instagram|translate|contact)\b", title, re.I):
            continue
        seen_urls.add(source_url)
        detail_text = _detail_text(source_url) if source_url.startswith("http") else ""
        combined = clean_text(" ".join([title, body_text[:1500], detail_text]))

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                description=detail_text,
                raw_context=combined,
            )
        )

    return jobs


def scrape_prt_custom(agency: dict) -> list[dict]:
    body_text, _ = _render_page(agency["jobs_url"], wait_ms=8000)
    listing = body_text.split("Working at Pittsburgh Regional Transit", 1)[0]
    chunks = re.split(r"\nApply\s+More Details\n|\nApply\s+More Details\s+|\nApply\s+.*?More Details\n", listing)
    jobs = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines or lines[0] in {"CURRENT JOB OPENINGS"} or re.fullmatch(r"\d+", lines[0]):
            continue
        if "CURRENT JOB OPENINGS" in lines[0] and len(lines) > 1:
            lines = lines[1:]
        title = clean_text(lines[0])
        if not title or len(title) > 140:
            continue
        description = clean_text(" ".join(lines[1:]))
        raw_context = clean_text(" ".join([title, description]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=agency["jobs_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                description=description,
                raw_context=raw_context,
            )
        )
    return jobs


def scrape_norta_custom(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=7000)
    section = body_text.split("We pride ourselves", 1)[0]
    matches = re.findall(
        r"\n([A-Z][^\n]{8,120})\n\s+Are you the .+? applying for it is a breeze\. (?:Please apply here\.|Best of luck! Apply here\.)",
        section,
        flags=re.DOTALL,
    )
    apply_links = [href for text, href in links if "apply here" in text.lower()]
    jobs = []
    for index, title in enumerate(matches):
        title = clean_text(title)
        source_url = apply_links[index] if index < len(apply_links) else agency["jobs_url"]
        raw_context = clean_text(" ".join([title, section]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                raw_context=raw_context,
            )
        )
    return jobs
