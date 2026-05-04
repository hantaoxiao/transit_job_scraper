from urllib.parse import urlencode, urlparse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, extract_salary, normalize_job


HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

PAGE_SIZE = 100
MAX_PAGES = 10


def _parse_oracle_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    site = "CX_1"
    if "sites" in parts:
        site_index = parts.index("sites")
        if len(parts) > site_index + 1:
            site = parts[site_index + 1]
    return f"{parsed.scheme}://{parsed.netloc}", site


def _strip_html(value: Optional[str]) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def _oracle_public_url(base: str, site: str, requisition_id: str) -> str:
    return f"{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{requisition_id}"


def _listing_url(base: str, site: str, offset: int) -> str:
    query = urlencode(
        {
            "onlyData": "true",
            "expand": "requisitionList",
            "finder": f"findReqs;siteNumber={site},sortBy=POSTING_DATES_DESC,limit={PAGE_SIZE},offset={offset}",
        }
    )
    return f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?{query}"


def _detail_url(base: str, site: str, requisition_id: str) -> str:
    query = urlencode(
        {
            "expand": "all",
            "onlyData": "true",
            "finder": f'ById;Id="{requisition_id}",siteNumber={site}',
        }
    )
    return f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?{query}"


def _coerce_listings(payload: dict) -> list[dict]:
    listings = []
    for item in payload.get("items", []):
        if isinstance(item.get("requisitionList"), list):
            listings.extend(item["requisitionList"])
        elif item.get("Title"):
            listings.append(item)
    return listings


def _fetch_detail(session: requests.Session, base: str, site: str, requisition_id: str) -> dict:
    try:
        response = session.get(_detail_url(base, site, requisition_id), headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("items"):
            return data["items"][0]
        return data
    except requests.RequestException:
        return {}
    except ValueError:
        return {}


def _location_from_detail(detail: dict, fallback: str) -> str:
    locations = detail.get("workLocation") or []
    if locations:
        location = locations[0]
        city = clean_text(location.get("TownOrCity"))
        state = clean_text(location.get("Region2"))
        if city and state:
            return f"{city}, {state}"
        if city:
            return city
    return clean_text(fallback)


def scrape_oracle(agency: dict) -> list[dict]:
    base, site = _parse_oracle_url(agency["jobs_url"])
    session = requests.Session()
    jobs = []
    seen_ids = set()

    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        response = session.get(_listing_url(base, site, offset), headers=HEADERS, timeout=30)
        response.raise_for_status()
        listings = _coerce_listings(response.json())
        if not listings:
            break

        for listing in listings:
            title = clean_text(listing.get("Title"))
            requisition_id = clean_text(
                listing.get("Id")
                or listing.get("RequisitionId")
                or listing.get("RequisitionNumber")
            )
            if not title or not requisition_id or requisition_id in seen_ids:
                continue
            seen_ids.add(requisition_id)

            detail = _fetch_detail(session, base, site, requisition_id)
            location = _location_from_detail(
                detail,
                detail.get("PrimaryLocation")
                or listing.get("PrimaryLocation")
                or detail.get("Location")
                or listing.get("Location"),
            )
            city = location.split(",")[0].strip() if location else agency["city"]
            description = _strip_html(
                detail.get("ExternalDescriptionStr")
                or detail.get("ExternalResponsibilitiesStr")
                or listing.get("ExternalResponsibilitiesStr")
            )
            salary_text = extract_salary(description)
            posted_date = clean_text(
                detail.get("ExternalPostedStartDate")
                or detail.get("PostedDate")
                or listing.get("PostedDate")
            )
            closing_date = clean_text(
                detail.get("ExternalPostedEndDate")
                or detail.get("PostingEndDate")
                or listing.get("PostingEndDate")
            )
            source_url = _oracle_public_url(base, site, requisition_id)
            raw_context = clean_text(
                " ".join(
                    str(value)
                    for value in [
                        title,
                        requisition_id,
                        location,
                        posted_date,
                        closing_date,
                        listing.get("JobFunction"),
                        listing.get("JobFamily"),
                        listing.get("Department"),
                        salary_text,
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
                    salary_text=salary_text,
                    posted_date=posted_date,
                    closing_date=closing_date,
                    category=clean_text(listing.get("JobFunction")) or None,
                    description=description,
                    raw_context=raw_context,
                    extra_fields={
                        "requisition_id": requisition_id,
                        "department": clean_text(listing.get("Department")),
                    },
                )
            )

        if len(listings) < PAGE_SIZE:
            break

    return jobs
