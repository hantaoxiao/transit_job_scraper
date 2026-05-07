from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, normalize_job


HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

PAGE_SIZE = 20
MAX_PAGES = 25


def _parse_workday_url(url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not parsed.netloc or len(path_parts) < 1:
        raise ValueError(f"Cannot parse Workday jobs URL: {url}")

    if path_parts[0].lower() == "recruiting" and len(path_parts) > 2:
        tenant = path_parts[1]
        site = path_parts[2]
        public_site_path = f"recruiting/{tenant}/{site}"
    elif path_parts[0].lower() in {"en-us", "en"} and len(path_parts) > 1:
        tenant = parsed.netloc.split(".", 1)[0]
        site = path_parts[1]
        public_site_path = "/".join(path_parts[:2])
    elif len(path_parts) == 1:
        tenant = parsed.netloc.split(".", 1)[0]
        site = path_parts[0]
        public_site_path = site
    else:
        tenant = path_parts[0]
        site = path_parts[1]
        public_site_path = "/".join(path_parts[:2])

    base = f"{parsed.scheme}://{parsed.netloc}"
    return base, tenant, site, public_site_path


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def _detail_url(base: str, tenant: str, site: str, external_path: str) -> str:
    path = external_path.lstrip("/")
    return f"{base}/wday/cxs/{tenant}/{site}/{path}"


def _public_url(base: str, public_site_path: str, external_path: str) -> str:
    if external_path.startswith("/"):
        external_path = external_path[1:]
    if external_path.startswith("job/"):
        return f"{base}/{public_site_path}/{external_path}"
    return f"{base}/{public_site_path}/job/{external_path}"


def _fetch_detail(session: requests.Session, base: str, tenant: str, site: str, external_path: str) -> dict:
    try:
        response = session.get(
            _detail_url(base, tenant, site, external_path),
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("jobPostingInfo", {})
    except requests.RequestException:
        return {}
    except ValueError:
        return {}


def _first_text(values) -> str:
    if isinstance(values, list) and values:
        first = values[0]
        if isinstance(first, dict):
            return clean_text(first.get("descriptor") or first.get("location") or first.get("name"))
        return clean_text(first)
    return clean_text(values)


def scrape_workday(agency: dict) -> list[dict]:
    base, tenant, site, public_site_path = _parse_workday_url(agency["jobs_url"])
    search_url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    session = requests.Session()
    jobs = []
    seen_urls = set()

    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        response = session.post(
            search_url,
            headers=HEADERS,
            json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        postings = payload.get("jobPostings", [])
        if not postings:
            break

        for posting in postings:
            title = clean_text(posting.get("title"))
            external_path = clean_text(posting.get("externalPath"))
            if not title or not external_path:
                continue

            source_url = _public_url(base, public_site_path, external_path)
            if source_url in seen_urls:
                continue
            seen_urls.add(source_url)

            detail = _fetch_detail(session, base, tenant, site, external_path)
            location = (
                clean_text(detail.get("location"))
                or _first_text(detail.get("additionalLocations"))
                or clean_text(posting.get("locationsText"))
            )
            city = location.split(",")[0].strip() if location else agency["city"]
            description = _strip_html(detail.get("jobDescription"))
            posted_date = clean_text(detail.get("startDate") or posting.get("postedOn"))
            req_id = clean_text(detail.get("jobReqId") or detail.get("jobRequisitionId"))
            raw_context = clean_text(
                " ".join(
                    str(value)
                    for value in [
                        title,
                        location,
                        posted_date,
                        req_id,
                        detail.get("jobProfile"),
                        detail.get("timeType"),
                        description,
                    ]
                    if value
                )
            )

            jobs.append(
                normalize_job(
                    title=title,
                    agency=agency["agency"],
                    city=city or agency["city"],
                    state=agency["state"],
                    source_url=source_url,
                    platform=agency["platform"],
                    posted_date=posted_date,
                    description=description,
                    raw_context=raw_context,
                    extra_fields={
                        "requisition_id": req_id,
                        "employment_type": clean_text(detail.get("timeType")),
                    },
                )
            )

        if len(postings) < PAGE_SIZE:
            break

    return jobs
