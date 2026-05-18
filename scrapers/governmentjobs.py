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


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


DETAIL_WORKERS = _env_int("GOVJOBS_DETAIL_WORKERS", 4)
REQUEST_RETRIES = _env_int("GOVJOBS_RETRIES", 2)
CONNECT_TIMEOUT = _env_int("GOVJOBS_CONNECT_TIMEOUT", 10)
READ_TIMEOUT = _env_int("GOVJOBS_READ_TIMEOUT", 30)
REQUEST_DELAY = _env_float("GOVJOBS_REQUEST_DELAY", 0.0)
AGENCY_DELAY = _env_float("GOVJOBS_AGENCY_DELAY", 0.0)
FETCH_DETAILS = os.getenv("GOVJOBS_FETCH_DETAILS", "").lower() in {"1", "true", "yes"}


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
    kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))

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

        time.sleep(min(attempt + 1, 4))

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


def _parse_listing_fields(item, agency: dict) -> dict:
    meta_items = [clean_text(node.get_text(" ", strip=True)) for node in item.select(".list-meta li")]
    meta_items = [text for text in meta_items if text]

    salary_text = next((text for text in meta_items if "$" in text), "")
    employment_type = ""
    if salary_text:
        employment_type = clean_text(re.split(r"\s+-\s+\$", salary_text, maxsplit=1)[0])
        if employment_type == salary_text:
            employment_type = ""
    else:
        employment_type = next(
            (
                text
                for text in meta_items
                if re.search(r"\b(full[- ]time|part[- ]time|temporary|regular|intern|seasonal)\b", text, re.I)
            ),
            "",
        )

    location = ""
    for text in meta_items:
        if text == salary_text:
            continue
        if re.match(r"^(Category|Department|Division|Cost Center|Executive Office):", text, flags=re.I):
            continue
        if text == employment_type:
            continue
        location = text
        break

    category = ""
    department = clean_text((item.select_one(".item-details-link") or {}).get("data-department-name", ""))
    for text in meta_items:
        if text.lower().startswith("category:"):
            category = clean_text(text.split(":", 1)[1])
        elif text.lower().startswith(("department:", "division:", "executive office:", "cost center:")) and not department:
            department = clean_text(text.split(":", 1)[1])

    description_node = item.select_one(".list-entry")
    description = clean_text(description_node.get_text(" ", strip=True)) if description_node else ""
    posted_node = item.select_one(".list-entry-starts")
    closing_node = item.select_one(".list-entry-ends")

    return {
        "salary_text": salary_text,
        "location": location,
        "posted_date": clean_text(posted_node.get_text(" ", strip=True)) if posted_node else "",
        "closing_date": clean_text(closing_node.get_text(" ", strip=True)) if closing_node else "",
        "description": description,
        "employment_type": employment_type,
        "department": department,
        "category": category,
    }


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
            listing = _parse_listing_fields(parent, agency) if parent else {}

            candidates.append(
                {
                    "title": title,
                    "source_url": full_url,
                    "raw_context": raw_context,
                    "listing": listing,
                }
            )

        if new_jobs == 0 or len(links) < 10:
            break
        if REQUEST_DELAY:
            time.sleep(REQUEST_DELAY)

    if not candidates:
        if AGENCY_DELAY:
            time.sleep(AGENCY_DELAY)
        return []

    details_by_url = {}
    detail_candidates = [
        item
        for item in candidates
        if FETCH_DETAILS and not item.get("listing", {}).get("salary_text")
    ]
    if detail_candidates:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            futures = {
                executor.submit(_detail_fields_for_url, item["source_url"]): item["source_url"]
                for item in detail_candidates
            }
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
        listing = item.get("listing", {})
        detail = details_by_url.get(source_url, {})
        city, state = _city_state_from_location(
            detail.get("location") or listing.get("location", ""),
            agency["city"],
            agency["state"],
        )
        description = detail.get("description") or listing.get("description", "")
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
                salary_text=detail.get("salary_text") or listing.get("salary_text", ""),
                posted_date=detail.get("posted_date") or listing.get("posted_date", ""),
                closing_date=detail.get("closing_date") or listing.get("closing_date", ""),
                description=description,
                raw_context=raw_context,
                extra_fields={
                    "requisition_id": detail.get("requisition_id", ""),
                    "employment_type": detail.get("employment_type") or listing.get("employment_type", ""),
                    "department": detail.get("department") or listing.get("department", ""),
                    "source_category": listing.get("category", ""),
                },
            )
        )

    if AGENCY_DELAY:
        time.sleep(AGENCY_DELAY)
    return jobs
