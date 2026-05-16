import csv
import os
from functools import lru_cache
from pathlib import Path

from normalizer import clean_text


CACHE_PATH = Path(os.getenv("SCRAPER_CACHE_PATH", "output/transit_jobs.csv"))
REFRESH_CACHED_DETAILS = os.getenv("SCRAPER_REFRESH_CACHED_DETAILS", "").lower() in {
    "1",
    "true",
    "yes",
}
DETAIL_CACHE_ENABLED = os.getenv("SCRAPER_DETAIL_CACHE", "1").lower() not in {
    "0",
    "false",
    "no",
}
KEEP_FIELDS = {
    "title",
    "agency",
    "city",
    "state",
    "source_url",
    "salary_text",
    "posted_date",
    "closing_date",
    "category",
    "description",
    "raw_context",
    "all_meaningful_info",
    "requisition_id",
    "employment_type",
    "department",
}


@lru_cache(maxsize=1)
def _cached_rows() -> tuple[dict, ...]:
    if not DETAIL_CACHE_ENABLED or REFRESH_CACHED_DETAILS or not CACHE_PATH.exists():
        return ()

    try:
        with CACHE_PATH.open(newline="", encoding="utf-8") as handle:
            return tuple(
                {key: value or "" for key, value in row.items() if key in KEEP_FIELDS}
                for row in csv.DictReader(handle)
            )
    except OSError:
        return ()


@lru_cache(maxsize=None)
def _agency_rows(agency_name: str) -> tuple[dict, ...]:
    agency_name = clean_text(agency_name)
    return tuple(row for row in _cached_rows() if row.get("agency") == agency_name)


def cached_job(
    agency_name: str,
    *,
    source_url: str = "",
    requisition_id: str = "",
    title: str = "",
) -> dict:
    rows = _agency_rows(agency_name)
    if not rows:
        return {}

    source_url = clean_text(source_url)
    requisition_id = clean_text(requisition_id)
    title = clean_text(title).lower()

    def title_matches(row: dict) -> bool:
        return not title or row.get("title", "").strip().lower() == title

    if source_url:
        matches = [row for row in rows if row.get("source_url", "").strip() == source_url and title_matches(row)]
        if matches:
            return max(matches, key=_detail_score)

        matches = [row for row in rows if row.get("source_url", "").strip() == source_url]
        if len(matches) == 1:
            return matches[0]

    if requisition_id:
        matches = [row for row in rows if row.get("requisition_id", "").strip() == requisition_id and title_matches(row)]
        if matches:
            return max(matches, key=_detail_score)

    return {}


def cached_detail_text(row: dict) -> str:
    if not row:
        return ""
    return clean_text(row.get("description") or row.get("all_meaningful_info") or row.get("raw_context"))


def has_cached_detail(row: dict) -> bool:
    if REFRESH_CACHED_DETAILS:
        return False
    return bool(
        row
        and (
            row.get("salary_text")
            or row.get("description")
            or row.get("all_meaningful_info")
            or row.get("raw_context")
        )
    )


def _detail_score(row: dict) -> int:
    return sum(
        1
        for field in (
            "salary_text",
            "description",
            "all_meaningful_info",
            "raw_context",
            "posted_date",
            "closing_date",
            "city",
            "state",
        )
        if row.get(field)
    )
