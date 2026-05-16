import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

SEARCH_ENDPOINT = "https://www.governmentjobs.com/careers/home/index"
MAX_PAGES = 30
def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DETAIL_WORKERS = _env_int("GOVJOBS_DETAIL_WORKERS", 4)
REQUEST_RETRIES = _env_int("GOVJOBS_RETRIES", 3)


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


def _agency_folder(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0].lower() == "careers":
        return path_parts[1]
    raise ValueError(f"Cannot parse GovernmentJobs agency folder from URL: {url}")


def _retryable_http_error(exc: requests.HTTPError) -> bool:
    response = exc.response
    return bool(response is not None and response.status_code in {429, 500, 502, 503, 504})


def _get_with_retries(session: requests.Session, url: str, **kwargs) -> requests.Response:
    last_error = None
    kwargs.setdefault("timeout", (12, 45))

    for attempt in range(REQUEST_RETRIES):
        try:
            response = session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.HTTPError as exc:
            last_error = exc
            if not _retryable_http_error(exc) or attempt == REQUEST_RETRIES - 1:
                raise
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            if attempt == REQUEST_RETRIES - 1:
                raise

        time.sleep(min(2 * (attempt + 1), 8))

    raise last_error or RuntimeError("GovernmentJobs request failed")


def _search_params(agency: dict, page: int) -> dict:
    parsed = urlparse(agency["jobs_url"])
    query = parse_qs(parsed.query)
    params = {"agency": _agency_folder(agency["jobs_url"])}

    for key in ("department", "department[]", "department[0]"):
        for value in query.get(key, []):
            params.setdefault("department", value)

    for key, value in agency.get("filters", {}).items():
        params[key] = value

    if page > 1:
        params["page"] = page

    return params


def _detail_fields(session: requests.Session, source_url: str) -> dict:
    try:
        response = _get_with_retries(session, source_url, headers=HEADERS)
    except requests.RequestException:
        return {}

    soup = BeautifulSoup(response.text, "lxml")
    text = clean_text(soup.get_text(" ", strip=True))

    fields = {}
    labels = {
        "Salary": "salary_text",
        "Location": "location",
        "Opening Date": "posted_date",
        "Closing Date": "closing_date",
        "Department": "department",
        "Job Type": "employment_type",
        "Job Number": "requisition_id",
    }
    for label, field in labels.items():
        value = _extract_label(text, label)
        if value:
            fields[field] = value

    description = soup.select_one(".job-details-info, #details-info, .job-description, .description")
    fields["description"] = clean_text(description.get_text(" ", strip=True)) if description else text
    return fields


def _detail_fields_for_url(source_url: str) -> dict:
    with requests.Session() as session:
        return _detail_fields(session, source_url)


def _extract_label(text: str, label: str) -> str:
    labels = (
        "Salary",
        "Location",
        "Job Type",
        "Job Number",
        "Department",
        "Division",
        "Opening Date",
        "Closing Date",
        "Licenses / Certifications",
        "Max Number of Applicants",
        "Union Affiliation",
        "Safety Sensitive",
        "On-Call or 24/7",
        "Essential Classification",
        "Note",
        "Job Conditions",
        "FLSA",
        "Bargaining Unit",
        "Description",
        "Benefits",
        "Questions",
    )
    lookahead = "|".join(re.escape(item) for item in labels if item != label)
    match = re.search(
        rf"\b{re.escape(label)}\s+(.+?)(?=\s+(?:{lookahead})\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    return clean_text(match.group(1)) if match else ""


def _city_state_from_location(location: str, fallback_city: str, fallback_state: str) -> tuple[str, str]:
    location = clean_text(location)
    if not location:
        return fallback_city, fallback_state

    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) >= 2:
        state_match = re.search(r"\b([A-Z]{2})\b(?:\s+\d{5})?\)?$", parts[-1])
        if state_match:
            return parts[-2], state_match.group(1)
        if len(parts[-1]) == 2:
            return parts[-2], parts[-1]
    return parts[0] if parts else fallback_city, fallback_state


def scrape_governmentjobs(agency: dict) -> list[dict]:
    """
    Starter scraper for GovernmentJobs / NEOGOV career pages.

    This is intentionally conservative. It grabs likely job links and normalizes them.
    If GovernmentJobs changes its page structure, update selectors here once and all
    GovernmentJobs agencies benefit.
    """
    session = requests.Session()
    candidates = []
    seen_urls = set()
    include_terms = [term.lower() for term in agency.get("include_terms", [])]
    exclude_terms = [term.lower() for term in agency.get("exclude_terms", [])]

    for page in range(1, MAX_PAGES + 1):
        response = _get_with_retries(
            session,
            SEARCH_ENDPOINT,
            params=_search_params(agency, page),
            headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
        )

        soup = BeautifulSoup(response.text, "lxml")
        links = soup.select('a[href*="/careers/"][href*="/jobs/"]')
        if not links:
            break

        new_jobs = 0
        for link in links:
            title = clean_text(link.get_text(" ", strip=True))
            href = link["href"]
            full_url = urljoin("https://www.governmentjobs.com", href)

            if not looks_like_link_text(title):
                continue
            if not looks_like_job_detail_url(full_url):
                continue
            if full_url in seen_urls:
                continue

            seen_urls.add(full_url)
            new_jobs += 1

            parent = link.find_parent("li", class_="list-item") or link.find_parent()
            raw_context = clean_text(parent.get_text(" ", strip=True)) if parent else title
            listing_salary = ""
            if parent:
                for item in parent.select(".list-meta li"):
                    text = clean_text(item.get_text(" ", strip=True))
                    if "$" in text:
                        listing_salary = text
                        break

            candidates.append(
                {
                    "title": title,
                    "source_url": full_url,
                    "raw_context": raw_context,
                    "listing_salary": listing_salary,
                }
            )

        if new_jobs == 0 or len(links) < 10:
            break

    if not candidates:
        return []

    details_by_url = {}
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(_detail_fields_for_url, item["source_url"]): item["source_url"] for item in candidates}
        for future in as_completed(futures):
            source_url = futures[future]
            try:
                details_by_url[source_url] = future.result()
            except Exception:
                details_by_url[source_url] = {}

    jobs = []
    for item in candidates:
        title = item["title"]
        source_url = item["source_url"]
        detail = details_by_url.get(source_url, {})
        city, state = _city_state_from_location(detail.get("location", ""), agency["city"], agency["state"])
        description = detail.get("description", "")
        raw_context = clean_text(" ".join([item["raw_context"], description]))
        search_text = f"{title} {raw_context}".lower()
        if include_terms and not any(term in search_text for term in include_terms):
            continue
        if exclude_terms and any(term in search_text for term in exclude_terms):
            continue

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=detail.get("salary_text") or item["listing_salary"],
                posted_date=detail.get("posted_date", ""),
                closing_date=detail.get("closing_date", ""),
                description=description,
                raw_context=raw_context,
                extra_fields={
                    "requisition_id": detail.get("requisition_id", ""),
                    "employment_type": detail.get("employment_type", ""),
                    "department": detail.get("department", ""),
                },
            )
        )

    return jobs
