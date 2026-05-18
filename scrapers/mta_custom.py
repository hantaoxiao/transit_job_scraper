import csv
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job, parse_salary, repair_split_money


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

SEARCH_URL = "https://careers.mta.org/search/jobs"
HOME_URL = "https://careers.mta.org/"
MAX_PAGES = 20
JINA_READER_PREFIX = "https://r.jina.ai/http://"
JINA_PER_PAGE = 100
BROWSER_PROFILE_DIR = Path(".mta_browser_profile")
JOB_LINK_SELECTOR = "a[href^='/jobs/'], a[href^='https://careers.mta.org/jobs/']"
DETAIL_READY_SELECTOR = "text=Description"
CLOUDFLARE_BLOCK_MARKERS = (
    "<title>Just a moment...</title>",
    "cf-browser-verification",
    "challenge-platform",
)
DETAIL_LABELS = (
    "Job ID",
    "Business Unit",
    "Location",
    "Regular/Temporary",
    "Department",
    "Date Posted",
    "Title",
    "First Date of Posting",
    "Authority",
    "Division/Unit",
    "Reports to",
    "Work Location",
    "Hours of Work",
    "Salary Range",
    "Compression",
    "Metro-North Posting Date",
    "Metro-North Closing Date",
)

DEFAULT_CACHE_PATH = Path("output/transit_jobs.csv")
CACHE_BOOL_FIELDS = {
    "salary_is_listed",
    "salary_is_comparable",
}
CACHE_NUMBER_FIELDS = {
    "salary_min",
    "salary_max",
    "salary_midpoint",
    "salary_annual_min_est",
    "salary_annual_max_est",
    "salary_annual_mid_est",
    "data_completeness_score",
}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


MTA_JINA_LIST_WORKERS = _env_int("MTA_JINA_LIST_WORKERS", 4)
MTA_JINA_DETAIL_WORKERS = _env_int("MTA_JINA_DETAIL_WORKERS", 8)
MTA_JINA_RETRIES = _env_int("MTA_JINA_RETRIES", 3)


def _extract_field(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}:\s*(.*?)(?=\s+[A-Z][A-Za-z ]+:\s*|$)", text)
    return clean_text(match.group(1)) if match else ""


def _extract_labeled_value(text: str, label: str) -> str:
    match = re.search(rf"(?im)^{re.escape(label)}\s*:\s*(.+)$", text)
    return clean_text(match.group(1)) if match else ""


def _extract_labeled_section(text: str, label: str) -> str:
    match = re.search(
        rf"(?ims)^{re.escape(label)}\s*:\s*(.+?)(?=^[A-Z][A-Za-z0-9 /&().,-]{{1,80}}\s*:\s*|\Z)",
        text,
    )
    return clean_text(match.group(1)) if match else ""


def _clean_compensation_section(text: str) -> str:
    text = repair_split_money(text)
    for heading in (
        "Responsibilities",
        "Education and Experience",
        "Desired Skills",
        "Selection Method",
        "Other Information",
        "Equal Employment Opportunity",
    ):
        text = re.split(rf"\s+\b{re.escape(heading)}\b(?:\s*:)?", text, maxsplit=1, flags=re.IGNORECASE)[0]
    return clean_text(text)


def _page_url(page: int) -> str:
    if page == 1:
        return SEARCH_URL
    return f"{SEARCH_URL}/in?page={page}"


def _is_cloudflare_blocked(html: str) -> bool:
    return any(marker in html for marker in CLOUDFLARE_BLOCK_MARKERS)


def _dedupe_jobs(jobs: list[dict]) -> list[dict]:
    deduped = []
    seen_ids = set()

    for job in jobs:
        if job["job_id"] in seen_ids:
            continue
        seen_ids.add(job["job_id"])
        deduped.append(job)

    return deduped


def _coerce_cached_job(row: dict) -> dict:
    job = dict(row)
    for field in CACHE_BOOL_FIELDS:
        if field in job:
            job[field] = str(job[field]).lower() in {"true", "1", "yes"}

    for field in CACHE_NUMBER_FIELDS:
        if field not in job or job[field] == "":
            continue
        try:
            job[field] = float(job[field])
        except (TypeError, ValueError):
            pass

    return job


def _mta_cache_paths() -> tuple[Path, ...]:
    raw_paths = []
    if os.getenv("SCRAPER_CACHE_PATHS"):
        raw_paths.extend(path for path in os.getenv("SCRAPER_CACHE_PATHS", "").split(os.pathsep) if path)
    if os.getenv("SCRAPER_CACHE_PATH"):
        raw_paths.append(os.getenv("SCRAPER_CACHE_PATH", ""))
    raw_paths.append(str(DEFAULT_CACHE_PATH))

    paths = []
    seen = set()
    for raw_path in raw_paths:
        path = Path(raw_path)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return tuple(paths)


def _cached_mta_job_score(job: dict) -> int:
    return sum(
        1
        for field in (
            "salary_text",
            "salary_is_listed",
            "description",
            "full_job_description",
            "all_meaningful_info",
            "raw_context",
            "posted_date",
            "closing_date",
            "mta_job_id",
        )
        if job.get(field)
    )


def _annual_salary_estimate(parsed_salary: dict) -> float:
    for field in ("salary_annual_max_est", "salary_max"):
        value = parsed_salary.get(field)
        if value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _repair_cached_salary_text(details: dict) -> None:
    salary_text = details.get("salary_text", "")
    repaired_salary_text = _clean_compensation_section(salary_text)
    if repaired_salary_text != clean_text(salary_text):
        details["salary_text"] = repaired_salary_text
        salary_text = repaired_salary_text

    context = details.get("all_meaningful_info") or details.get("full_job_description") or ""
    extracted = extract_salary(context)
    if not extracted:
        return

    current_salary = parse_salary(salary_text)
    extracted_salary = parse_salary(extracted)
    if not extracted_salary.get("salary_is_comparable"):
        return

    current_estimate = _annual_salary_estimate(current_salary)
    extracted_estimate = _annual_salary_estimate(extracted_salary)
    if (
        not current_salary.get("salary_is_comparable")
        or current_estimate < 30000
        or extracted_estimate > current_estimate * 2
    ):
        details["salary_text"] = extracted


def _cached_job_details(job: dict) -> dict:
    detail_keys = [
        "all_meaningful_info",
        "business_unit",
        "closing_date",
        "department",
        "detail_location",
        "division_unit",
        "employment_type",
        "full_job_description",
        "hours_of_work",
        "mta_job_id",
        "reports_to",
        "salary_text",
        "work_location",
    ]
    details = {key: job.get(key, "") for key in detail_keys if job.get(key)}
    if job.get("description") and not details.get("full_job_description"):
        details["full_job_description"] = job["description"]
    if job.get("raw_context") and not details.get("all_meaningful_info"):
        details["all_meaningful_info"] = job["raw_context"]
    _repair_cached_salary_text(details)
    return details


def _load_existing_mta_cache(agency: dict) -> dict[str, dict]:
    cached_jobs = {}
    for path in _mta_cache_paths():
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if row.get("agency") != agency["agency"] or not row.get("source_url"):
                        continue
                    job = _coerce_cached_job(row)
                    source_url = row["source_url"]
                    if source_url not in cached_jobs or _cached_mta_job_score(job) > _cached_mta_job_score(cached_jobs[source_url]):
                        cached_jobs[source_url] = job
        except OSError:
            continue
    return cached_jobs


def _discover_search_urls(session: requests.Session) -> list[str]:
    """Discover MTA search pages from the homepage as a fallback.

    Some environments receive a 403 on /search/jobs. Category pages can
    still be reachable, so we crawl links from the homepage navigation.
    """
    response = session.get(HOME_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    urls = [SEARCH_URL]
    seen = {SEARCH_URL}

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not href.startswith("/search/") or not href.endswith("/jobs"):
            continue
        full_url = urljoin(HOME_URL, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        urls.append(full_url)

    return urls


def _discover_search_urls_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = [SEARCH_URL]
    seen = {SEARCH_URL}

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if not href.startswith("/search/") or not href.endswith("/jobs"):
            continue
        full_url = urljoin(HOME_URL, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        urls.append(full_url)

    return urls


def _is_job_href(href: str) -> bool:
    return urlparse(href).path.startswith("/jobs/")


def _location_to_city_state(location: str, agency: dict) -> tuple[str, str]:
    city = agency["city"]
    state = agency["state"]

    if location:
        location = location.replace(", United States", "")
        city_state = [part.strip() for part in location.split(",") if part.strip()]
        if city_state:
            city = city_state[0]
        if len(city_state) > 1:
            state = city_state[1]

    return city, state


def _meaningful_lines_from_text(text: str) -> list[str]:
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    if "Back to job search" in lines:
        lines = lines[lines.index("Back to job search") + 1 :]
    if "Apply Now" in lines:
        lines = lines[: lines.index("Apply Now")]

    skipped = {
        "Skip to main content",
        "Careers",
        "All Jobs",
        "Jobs by Area",
        "Saved Jobs",
        "Benefits",
        "Diversity & Inclusion",
        "Veterans",
        "Events",
        "Application Status",
    }
    lines = [line for line in lines if line not in skipped]
    combined_lines = []
    labels = set(DETAIL_LABELS)
    i = 0

    while i < len(lines):
        line = lines[i]
        label = line.rstrip(":")
        inline_label = next((name for name in labels if line.startswith(f"{name}:")), "")

        if label in labels and line.endswith(":") and i + 1 < len(lines):
            combined_lines.append(f"{line} {lines[i + 1]}")
            i += 2
            continue

        if (label in labels or inline_label) and i + 1 < len(lines) and lines[i + 1].startswith("- "):
            combined_lines.append(f"{line} {lines[i + 1]}")
            i += 2
            continue

        combined_lines.append(line)
        i += 1

    return combined_lines


def _parse_detail_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    lines = _meaningful_lines_from_text(text)
    meaningful_text = "\n".join(lines)

    details = {
        "all_meaningful_info": meaningful_text,
        "full_job_description": "",
        "mta_job_id": _extract_labeled_value(meaningful_text, "Job ID"),
        "business_unit": _extract_labeled_value(meaningful_text, "Business Unit"),
        "employment_type": _extract_labeled_value(meaningful_text, "Regular/Temporary"),
        "department": _extract_labeled_value(meaningful_text, "Department"),
        "authority": _extract_labeled_value(meaningful_text, "Authority"),
        "division_unit": _extract_labeled_value(meaningful_text, "Division/Unit"),
        "reports_to": _extract_labeled_value(meaningful_text, "Reports to"),
        "work_location": _extract_labeled_value(meaningful_text, "Work Location"),
        "hours_of_work": _extract_labeled_value(meaningful_text, "Hours of Work"),
    }

    location = _extract_labeled_value(meaningful_text, "Location")
    if location:
        details["detail_location"] = location

    posted_date = (
        _extract_labeled_value(meaningful_text, "Date Posted")
        or _extract_labeled_value(meaningful_text, "First Date of Posting")
        or _extract_labeled_value(meaningful_text, "Metro-North Posting Date")
    )
    if posted_date:
        details["posted_date"] = posted_date

    closing_date = _extract_labeled_value(meaningful_text, "Metro-North Closing Date")
    if closing_date:
        details["closing_date"] = closing_date

    salary_text = _extract_labeled_section(meaningful_text, "Salary Range")
    if salary_text:
        details["salary_text"] = _clean_compensation_section(salary_text)

    if "Description" in lines:
        details["full_job_description"] = "\n".join(lines[lines.index("Description") + 1 :])

    for label in DETAIL_LABELS:
        value = _extract_labeled_value(meaningful_text, label)
        if value:
            key = "mta_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
            details[key] = details["salary_text"] if label == "Salary Range" and details.get("salary_text") else value

    return details


def _build_mta_job(summary: dict, agency: dict, details: Optional[dict] = None) -> dict:
    details = details or {}
    location = details.get("detail_location") or summary.get("location", "")
    city, state = _location_to_city_state(location, agency)

    all_info = details.get("all_meaningful_info") or summary.get("raw_context", "")
    department = details.get("department") or summary.get("department", "")
    description = details.get("full_job_description") or department

    extra_fields = {key: value for key, value in details.items() if key != "salary_text"}

    return normalize_job(
        title=summary["title"],
        agency=agency["agency"],
        city=city,
        state=state,
        source_url=summary["source_url"],
        platform=agency["platform"],
        salary_text=details.get("salary_text"),
        posted_date=details.get("posted_date") or summary.get("posted_date", ""),
        closing_date=details.get("closing_date", ""),
        description=description,
        raw_context=all_info,
        extra_fields=extra_fields,
    )


def _parse_search_page(html: str, agency: dict, normalize: bool = True) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not _is_job_href(href):
            continue

        title = clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        source_url = urljoin(SEARCH_URL, href)
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        container = link.find_parent(["article", "li", "tr", "div"])
        raw_context = clean_text(container.get_text(" ", strip=True)) if container else title
        location = _extract_field(raw_context, "Location")
        posted_date = _extract_field(raw_context, "Date Posted")
        department = _extract_field(raw_context, "Department")

        summary = {
            "title": title,
            "source_url": source_url,
            "location": location,
            "posted_date": posted_date,
            "department": department,
            "raw_context": raw_context,
        }

        jobs.append(_build_mta_job(summary, agency) if normalize else summary)

    return jobs


def _jina_url(url: str) -> str:
    return f"{JINA_READER_PREFIX}{url}"


def _is_jina_unusable_text(text: str) -> bool:
    normalized = clean_text(text).lower()
    if not normalized:
        return True
    return any(
        marker in normalized
        for marker in [
            "enable javascript and cookies to continue",
            "just a moment",
            "target url returned error 403",
            "checking if the site connection is secure",
            "verify you are human",
        ]
    )


def _jina_text(url: str) -> str:
    last_error = None
    for attempt in range(MTA_JINA_RETRIES):
        try:
            response = requests.get(_jina_url(url), headers=HEADERS, timeout=90)
            response.raise_for_status()
            if "Markdown Content:" in response.text:
                text = response.text.split("Markdown Content:", 1)[1]
            else:
                text = response.text
            if _is_jina_unusable_text(text):
                raise requests.HTTPError("MTA Jina fallback returned a challenge page", response=response)
            return text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == MTA_JINA_RETRIES - 1:
                raise
            time.sleep(min(3 * (attempt + 1), 10))
    raise last_error or RuntimeError("MTA Jina fallback request failed")


def _jina_search_url(page: int) -> str:
    if page == 1:
        return f"{SEARCH_URL}?per_page={JINA_PER_PAGE}"
    return f"{SEARCH_URL}/in?page={page}&per_page={JINA_PER_PAGE}"


def _parse_jina_total_pages(text: str) -> int:
    match = re.search(r"Showing\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+results", text, flags=re.IGNORECASE)
    if not match:
        return 1
    total = int(match.group(1))
    return max(1, min(MAX_PAGES, (total + JINA_PER_PAGE - 1) // JINA_PER_PAGE))


def _parse_jina_search_page(text: str, agency: dict, normalize: bool = False) -> list[dict]:
    jobs = []
    seen_urls = set()
    pattern = re.compile(
        r"\[([^\]]+)\]\((https://careers\.mta\.org/jobs/[^)]+)\)\s+"
        r"Job ID:\s*([^\n]+)\s+"
        r"Location:\s*([^\n]+)\s+"
        r"Department:\s*([^\n]*)\s+"
        r"Date Posted:\s*([^\n]+)",
        flags=re.DOTALL,
    )

    for title, source_url, job_id, location, department, posted_date in pattern.findall(text):
        source_url = source_url.split("#", 1)[0]
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        raw_context = clean_text(
            " ".join(
                [
                    f"Job ID: {job_id}",
                    f"Location: {location}",
                    f"Department: {department}",
                    f"Date Posted: {posted_date}",
                ]
            )
        )
        summary = {
            "title": clean_text(title),
            "source_url": source_url,
            "location": clean_text(location),
            "posted_date": clean_text(posted_date),
            "department": clean_text(department),
            "raw_context": raw_context,
        }
        jobs.append(_build_mta_job(summary, agency) if normalize else summary)

    return jobs


def _jina_detail_to_plain_text(markdown: str) -> str:
    def label_replacement(match: re.Match) -> str:
        return f"\n{match.group(1).rstrip(':')}: "

    text = re.sub(r"\*\*([^*]+)\*\*\s*:?\s*", label_replacement, markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>`]+", " ", text)
    return "\n".join(clean_text(line) for line in text.splitlines() if clean_text(line))


def _parse_jina_detail_page(markdown: str) -> dict:
    meaningful_text = _jina_detail_to_plain_text(markdown)
    details = {
        "all_meaningful_info": meaningful_text,
        "full_job_description": meaningful_text,
        "department": _extract_labeled_value(meaningful_text, "Department"),
        "authority": _extract_labeled_value(meaningful_text, "Authority"),
        "division_unit": _extract_labeled_value(meaningful_text, "Division/Unit"),
        "reports_to": _extract_labeled_value(meaningful_text, "Reporting Manager (If Applicable)"),
        "work_location": _extract_labeled_value(meaningful_text, "Work Location"),
        "hours_of_work": _extract_labeled_value(meaningful_text, "Hours of Work"),
    }

    compensation = (
        _extract_labeled_section(meaningful_text, "Salary Range")
        or _extract_labeled_section(meaningful_text, "Compensation")
        or _extract_labeled_section(meaningful_text, "Salary")
    )
    if compensation:
        details["salary_text"] = _clean_compensation_section(compensation)

    closing_date = (
        _extract_labeled_value(meaningful_text, "Deadline (if Applicable)")
        or _extract_labeled_value(meaningful_text, "Metro-North Closing Date")
    )
    if closing_date:
        details["closing_date"] = closing_date

    return {key: value for key, value in details.items() if value}


def _fetch_jina_detail(source_url: str) -> dict:
    try:
        return _parse_jina_detail_page(_jina_text(source_url))
    except requests.RequestException:
        return {}


def _cached_mta_jobs_or_empty(agency: dict, reason: str, cached_jobs: Optional[dict[str, dict]] = None) -> list[dict]:
    cached_jobs = cached_jobs if cached_jobs is not None else _load_existing_mta_cache(agency)
    if cached_jobs:
        print(f"{reason}; using {len(cached_jobs)} cached MTA jobs instead.")
        return _dedupe_jobs(list(cached_jobs.values()))

    print(f"{reason}; no cached MTA jobs available.")
    return []


def _scrape_mta_jina(agency: dict) -> list[dict]:
    print("MTA blocked direct requests; using live text-rendered MTA listing fallback.")
    cached_jobs = _load_existing_mta_cache(agency)

    try:
        first_page = _jina_text(_jina_search_url(1))
    except requests.RequestException:
        return _cached_mta_jobs_or_empty(agency, "MTA Jina listing fallback was blocked", cached_jobs)

    summaries = _parse_jina_search_page(first_page, agency, normalize=False)
    if not summaries:
        return _cached_mta_jobs_or_empty(agency, "MTA Jina listing fallback returned no parseable jobs", cached_jobs)

    total_pages = _parse_jina_total_pages(first_page)
    failed_pages = []
    merge_cached_remainder = bool(cached_jobs and total_pages > 1)

    if merge_cached_remainder:
        print(
            f"MTA Jina fallback read {len(summaries)} listings from the first per_page={JINA_PER_PAGE} page; "
            "merging with cached MTA jobs instead of fetching later pages."
        )
    elif total_pages > 1:
        with ThreadPoolExecutor(max_workers=min(MTA_JINA_LIST_WORKERS, total_pages - 1)) as executor:
            futures = {executor.submit(_jina_text, _jina_search_url(page)): page for page in range(2, total_pages + 1)}
            for future in as_completed(futures):
                page = futures[future]
                try:
                    page_summaries = _parse_jina_search_page(future.result(), agency, normalize=False)
                except requests.RequestException:
                    failed_pages.append(page)
                    continue
                if not page_summaries:
                    failed_pages.append(page)
                    continue
                summaries.extend(page_summaries)

    if failed_pages and cached_jobs:
        pages = ", ".join(str(page) for page in sorted(failed_pages))
        return _cached_mta_jobs_or_empty(
            agency,
            f"MTA Jina listing fallback could not read all result pages ({pages})",
            cached_jobs,
        )
    if failed_pages:
        pages = ", ".join(str(page) for page in sorted(failed_pages))
        raise RuntimeError(f"MTA Jina listing fallback could not read pages {pages} and no MTA cache was available")

    deduped_summaries = []
    seen_urls = set()
    for summary in summaries:
        source_url = summary["source_url"]
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        deduped_summaries.append(summary)

    summary_by_url = {summary["source_url"]: summary for summary in deduped_summaries}
    new_urls = [source_url for source_url in summary_by_url if source_url not in cached_jobs]
    details_by_url = {}

    if new_urls:
        print(f"Fetching live MTA details for {len(new_urls)} new or uncached jobs.")
        with ThreadPoolExecutor(max_workers=min(MTA_JINA_DETAIL_WORKERS, len(new_urls))) as executor:
            futures = {executor.submit(_fetch_jina_detail, source_url): source_url for source_url in new_urls}
            for future in as_completed(futures):
                details_by_url[futures[future]] = future.result()

    jobs = []
    reused_details = 0
    for source_url, summary in summary_by_url.items():
        if source_url in details_by_url:
            jobs.append(_build_mta_job(summary, agency, details_by_url[source_url]))
        elif source_url in cached_jobs:
            reused_details += 1
            jobs.append(_build_mta_job(summary, agency, _cached_job_details(cached_jobs[source_url])))
        else:
            jobs.append(_build_mta_job(summary, agency))

    preserved_cached = 0
    if merge_cached_remainder:
        for source_url, cached_job in cached_jobs.items():
            if source_url in summary_by_url:
                continue
            jobs.append(cached_job)
            preserved_cached += 1

    if reused_details:
        print(f"Reused cached MTA details for {reused_details}/{len(summary_by_url)} currently listed jobs.")
    if preserved_cached:
        print(f"Preserved {preserved_cached} cached MTA jobs beyond the first Jina listing page.")

    return _dedupe_jobs(jobs)


def _scrape_mta_requests(agency: dict) -> list[dict]:
    jobs = []
    session = requests.Session()
    search_urls = _discover_search_urls(session)

    for search_url in search_urls:
        for page in range(1, MAX_PAGES + 1):
            page_url = search_url if page == 1 else f"{search_url}/in?page={page}"
            try:
                response = session.get(page_url, headers=HEADERS, timeout=30)
                response.raise_for_status()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 403:
                    if page == 1:
                        break
                    return jobs
                raise

            if _is_cloudflare_blocked(response.text):
                raise requests.HTTPError("Cloudflare challenge page returned", response=response)

            page_jobs = _parse_search_page(response.text, agency)
            if not page_jobs:
                break

            jobs.extend(page_jobs)

            time.sleep(0.5)

    return _dedupe_jobs(jobs)


def _wait_for_mta_browser_page(page, url: str, selector: Optional[str] = None) -> str:
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)

    if selector:
        try:
            page.wait_for_selector(selector, timeout=15_000)
        except Exception:
            pass

    html = page.content()
    if _is_cloudflare_blocked(html):
        print("MTA returned a browser challenge. Complete it in the opened browser window.")
        wait_selector = selector or "body"
        page.wait_for_selector(wait_selector, timeout=120_000)
        html = page.content()

    return html


def _scrape_mta_browser(agency: dict) -> list[dict]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "MTA needs Playwright for browser fallback. Run: pip install -r requirements.txt; playwright install chromium"
        ) from exc

    summaries = []
    cached_jobs = _load_existing_mta_cache(agency)

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=False,
                viewport={"width": 1440, "height": 1000},
            )
        except PlaywrightError as exc:
            if cached_jobs:
                print(f"MTA browser fallback unavailable; using {len(cached_jobs)} cached MTA jobs")
                return _dedupe_jobs(list(cached_jobs.values()))
            raise RuntimeError(
                "MTA needs the browser fallback. Run: playwright install chromium"
            ) from exc

        page = context.new_page()

        _wait_for_mta_browser_page(page, HOME_URL, "a[href^='/search/']")
        search_urls = [SEARCH_URL]

        for search_url in search_urls:
            for page_num in range(1, MAX_PAGES + 1):
                page_url = search_url if page_num == 1 else f"{search_url}/in?page={page_num}"
                html = _wait_for_mta_browser_page(page, page_url, JOB_LINK_SELECTOR)
                page_summaries = _parse_search_page(html, agency, normalize=False)
                if not page_summaries:
                    break

                summaries.extend(page_summaries)
                time.sleep(0.5)

        summaries = _dedupe_jobs([_build_mta_job(summary, agency) for summary in summaries])
        summary_by_url = {job["source_url"]: job for job in summaries}
        jobs = []
        skipped_details = 0

        for index, source_url in enumerate(summary_by_url, start=1):
            if source_url in cached_jobs:
                jobs.append(cached_jobs[source_url])
                skipped_details += 1
                continue

            if index == 1 or index % 25 == 0:
                print(f"Enriching MTA job details {index}/{len(summary_by_url)}")

            detail_html = _wait_for_mta_browser_page(page, source_url, DETAIL_READY_SELECTOR)
            details = _parse_detail_page(detail_html)
            summary = {
                "title": summary_by_url[source_url]["title"],
                "source_url": source_url,
                "location": summary_by_url[source_url]["raw_context"],
                "posted_date": summary_by_url[source_url]["posted_date"],
                "department": summary_by_url[source_url]["description"],
                "raw_context": summary_by_url[source_url]["raw_context"],
            }
            jobs.append(_build_mta_job(summary, agency, details))
            time.sleep(0.2)

        if skipped_details:
            print(f"Used cached MTA details for {skipped_details}/{len(summary_by_url)} jobs")

        context.close()

    return _dedupe_jobs(jobs)


def scrape_mta(agency: dict) -> list[dict]:
    try:
        return _scrape_mta_requests(agency)
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if response is None or response.status_code != 403:
            raise

        if os.getenv("GITHUB_ACTIONS", "").lower() == "true" or os.getenv("CI", "").lower() == "true":
            return _scrape_mta_jina(agency)

        print("MTA blocked the requests scraper; trying local browser fallback.")
        return _scrape_mta_browser(agency)
