from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from normalizer import clean_text, normalize_job


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

DETAIL_BASE = "https://careers.wmata.com/psc/careers/EXT_APPLICANT/HRMS/c/HRS_HRAM.HRS_CE.GBL"


def _detail_url(job_id: str) -> str:
    params = {
        "Action": "A",
        "HRS_PERSON_ID": "0",
        "JobOpeningId": job_id,
        "NoCrumbs": "yes",
        "PAGE": "HRS_CE_JOB_DTL",
        "Page": "HRS_CE_JOB_DTL",
        "PortalHostNode": "CAREERS",
        "PortalRegistryName": "EXT_APPLICANT",
        "PortalServletURI": "https://careers.wmata.com/psp/careers/",
        "PortalURI": "https://careers.wmata.com/psc/careers/",
        "PostingSeq": "1",
        "SiteId": "1",
    }
    return f"{DETAIL_BASE}?{urlencode(params)}"


def scrape_peoplesoft_wmata(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    jobs = []

    for title_el in soup.select('a[id^="POSTINGTITLE$"]'):
        suffix = title_el.get("id", "").split("$")[-1]
        title = clean_text(title_el.get_text(" ", strip=True))
        job_id_el = soup.select_one(f'[id="JOBNUMBER${suffix}"]')
        location_el = soup.select_one(f'[id="HRS_LOCATION_DESCR${suffix}"]')
        posted_el = soup.select_one(f'[id="OPENED${suffix}"]')

        requisition_id = clean_text(job_id_el.get_text(" ", strip=True)) if job_id_el else ""
        if not title or not requisition_id:
            continue

        location = clean_text(location_el.get_text(" ", strip=True)) if location_el else agency["city"]
        posted_date = clean_text(posted_el.get_text(" ", strip=True)) if posted_el else ""
        city = agency["city"]
        state = agency["state"]
        if location.startswith("VA"):
            city, state = "Alexandria", "VA"
        elif location.startswith("DC"):
            city, state = "Washington", "DC"
        elif location.startswith("MD"):
            city, state = "Landover", "MD"

        raw_context = clean_text(" ".join([title, requisition_id, location, posted_date]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=_detail_url(requisition_id),
                platform=agency["platform"],
                posted_date=posted_date,
                raw_context=raw_context,
                extra_fields={"requisition_id": requisition_id},
            )
        )

    return jobs
