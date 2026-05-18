import csv
import os
from functools import lru_cache
from pathlib import Path

from normalizer import clean_text


DEFAULT_CACHE_PATH = Path("output/transit_jobs.csv")
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


def _cache_paths() -> tuple[Path, ...]:
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


def _cache_key(row: dict) -> tuple[str, str, str]:
    return (
        clean_text(row.get("agency")),
        clean_text(row.get("source_url")),
        clean_text(row.get("title")).lower(),
    )


@lru_cache(maxsize=1)
def _cached_rows() -> tuple[dict, ...]:
    if not DETAIL_CACHE_ENABLED or REFRESH_CACHED_DETAILS:
        return ()

    best_rows = {}
    for path in _cache_paths():
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    kept = {key: value or "" for key, value in row.items() if key in KEEP_FIELDS}
                    key = _cache_key(kept)
                    if key not in best_rows or _detail_score(kept) > _detail_score(best_rows[key]):
                        best_rows[key] = kept
        except OSError:
            continue

    return tuple(best_rows.values())


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
