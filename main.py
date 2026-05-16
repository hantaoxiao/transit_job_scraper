from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import multiprocessing as mp
import os
import signal
import tempfile
import time
import uuid

import pandas as pd

from agencies import AGENCIES
from scrapers.governmentjobs import scrape_governmentjobs
from scrapers.workday import scrape_workday
from scrapers.oracle import scrape_oracle
from scrapers.taleo import scrape_taleo
from scrapers.successfactors import scrape_successfactors
from scrapers.mta_custom import scrape_mta
from scrapers.ukg import scrape_ukg
from scrapers.salesforce_custom import scrape_salesforce_custom
from scrapers.sf_careers import scrape_sf_careers
from scrapers.peoplesoft_wmata import scrape_peoplesoft_wmata
from scrapers.jobs2web import scrape_jobs2web
from scrapers.jobvite import scrape_jobvite
from scrapers.cadient import scrape_cadient
from scrapers.browser_jobboard import (
    scrape_adp,
    scrape_applicantpro,
    scrape_calopps,
    scrape_cdta_custom,
    scrape_dayforce,
    scrape_foothill_custom,
    scrape_gcrta_custom,
    scrape_icims,
    scrape_miami_dade_dtpw,
    scrape_munis_selfservice,
    scrape_nfta_custom,
    scrape_norta_custom,
    scrape_panynj_custom,
    scrape_prt_custom,
    scrape_static_job_links,
    scrape_static_text_jobs,
    scrape_taleo_v2,
    scrape_uta_custom,
    scrape_via_custom,
)


SCRAPER_MAP = {
    "governmentjobs": scrape_governmentjobs,
    "workday": scrape_workday,
    "oracle": scrape_oracle,
    "taleo": scrape_taleo,
    "successfactors": scrape_successfactors,
    "mta_custom": scrape_mta,
    "ukg": scrape_ukg,
    "salesforce_custom": scrape_salesforce_custom,
    "sf_careers": scrape_sf_careers,
    "peoplesoft_wmata": scrape_peoplesoft_wmata,
    "jobs2web": scrape_jobs2web,
    "jobvite": scrape_jobvite,
    "cadient": scrape_cadient,
    "adp": scrape_adp,
    "applicantpro": scrape_applicantpro,
    "cdta_custom": scrape_cdta_custom,
    "capmetro_custom": scrape_static_job_links,
    "calopps": scrape_calopps,
    "careersingovernment": scrape_static_job_links,
    "charlotte_custom": scrape_static_job_links,
    "dayforce": scrape_dayforce,
    "detroit_custom": scrape_static_job_links,
    "foothill_custom": scrape_foothill_custom,
    "gcrta_custom": scrape_gcrta_custom,
    "grtc_custom": scrape_static_job_links,
    "madison_custom": scrape_static_job_links,
    "metra_custom": scrape_cadient,
    "icims": scrape_icims,
    "munis_selfservice": scrape_munis_selfservice,
    "nfta_custom": scrape_nfta_custom,
    "norta_custom": scrape_norta_custom,
    "oracle_legacy": scrape_gcrta_custom,
    "panynj_custom": scrape_panynj_custom,
    "peoplesoft_miami": scrape_miami_dade_dtpw,
    "prt_custom": scrape_prt_custom,
    "rta_new_orleans_custom": scrape_norta_custom,
    "sorta_custom": scrape_static_job_links,
    "static_job_links": scrape_static_job_links,
    "static_text": scrape_static_text_jobs,
    "taleo_v2": scrape_taleo_v2,
    "transdev": scrape_static_job_links,
    "uta_custom": scrape_uta_custom,
    "via_custom": scrape_via_custom,
}


PARALLEL_PLATFORMS = {
    "governmentjobs",
    "workday",
    "oracle",
    "taleo",
    "successfactors",
    "ukg",
    "salesforce_custom",
    "sf_careers",
    "jobs2web",
    "jobvite",
    "cadient",
    "calopps",
    "cdta_custom",
    "icims",
    "munis_selfservice",
    "nfta_custom",
    "norta_custom",
    "panynj_custom",
    "static_text",
    "uta_custom",
}

def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


DEFAULT_SCRAPER_WORKERS = _env_int("SCRAPER_WORKERS", 6)
DEFAULT_GOVJOBS_AGENCY_WORKERS = _env_int("GOVJOBS_AGENCY_WORKERS", 2)
DEFAULT_RISKY_SCRAPER_TIMEOUT = _env_int("RISKY_SCRAPER_TIMEOUT", 180)
SERIAL_PLATFORMS = {"mta_custom"}
RISKY_PLATFORM_TIMEOUTS = {
    "mta_custom": 300,
    "peoplesoft_miami": 90,
    "via_custom": 45,
    "applicantpro": 60,
    "adp": 60,
    "dayforce": 45,
}


def write_site_data(df: pd.DataFrame, site_dir: Path) -> None:
    site_dir.mkdir(exist_ok=True)
    site_df = df.drop(
        columns=["salary_midpoint", "salary_annual_mid_est"],
        errors="ignore",
    )
    records = site_df.fillna("").to_dict(orient="records")
    agencies = []

    if not df.empty:
        for agency, group in df.groupby("agency"):
            total = len(group)
            salary_listed = int(group.get("salary_is_listed", pd.Series(dtype=bool)).fillna(False).sum())
            comparable_salary = int(group.get("salary_is_comparable", pd.Series(dtype=bool)).fillna(False).sum())
            closing_dates = int(group.get("closing_date", pd.Series(dtype=str)).fillna("").astype(bool).sum())
            agencies.append(
                {
                    "agency": agency,
                    "total_jobs": total,
                    "salary_listed_pct": round(salary_listed / total * 100) if total else 0,
                    "comparable_salary_pct": round(comparable_salary / total * 100) if total else 0,
                    "closing_date_pct": round(closing_dates / total * 100) if total else 0,
                }
            )

    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "jobs": records,
        "agency_metrics": sorted(agencies, key=lambda item: item["agency"]),
    }

    data_path = site_dir / "data.js"
    data_path.write_text(
        "window.TRANSIT_JOBS_DATA = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )


def _scrape_agency(agency: dict) -> dict:
    started_at = time.perf_counter()
    platform = agency["platform"]

    if agency.get("skip_scrape_reason"):
        return {
            "agency": agency["agency"],
            "platform": platform,
            "jobs": [],
            "elapsed": 0,
            "error": agency["skip_scrape_reason"],
        }

    scraper = SCRAPER_MAP.get(platform)

    if scraper is None:
        return {
            "agency": agency["agency"],
            "platform": platform,
            "jobs": [],
            "elapsed": 0,
            "error": f"No scraper found for {agency['agency']} / {platform}",
        }

    try:
        jobs = scraper(agency)
        return {
            "agency": agency["agency"],
            "platform": platform,
            "jobs": jobs,
            "elapsed": time.perf_counter() - started_at,
            "error": "",
        }
    except Exception as exc:
        return {
            "agency": agency["agency"],
            "platform": platform,
            "jobs": [],
            "elapsed": time.perf_counter() - started_at,
            "error": str(exc),
        }


def _agency_timeout_seconds(agency: dict) -> int:
    if agency.get("timeout_seconds"):
        try:
            return max(1, int(agency["timeout_seconds"]))
        except (TypeError, ValueError):
            pass
    return RISKY_PLATFORM_TIMEOUTS.get(agency["platform"], DEFAULT_RISKY_SCRAPER_TIMEOUT)


def _scrape_agency_process_worker(agency: dict, result_path: str) -> None:
    if hasattr(os, "setsid"):
        os.setsid()
    try:
        result = _scrape_agency(agency)
    except BaseException as exc:
        result = {
            "agency": agency.get("agency", ""),
            "platform": agency.get("platform", ""),
            "jobs": [],
            "elapsed": 0,
            "error": f"Isolated scraper worker crashed: {exc}",
        }
    Path(result_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _stop_process_tree(process: mp.Process) -> None:
    if process.pid and hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            process.terminate()
    else:
        process.terminate()

    process.join(5)
    if process.is_alive():
        if process.pid and hasattr(os, "killpg"):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            except OSError:
                process.kill()
        else:
            process.kill()
        process.join(5)


def _scrape_agency_isolated(agency: dict) -> dict:
    if agency.get("skip_scrape_reason"):
        return _scrape_agency(agency)

    started_at = time.perf_counter()
    timeout = _agency_timeout_seconds(agency)
    context = mp.get_context("spawn")
    result_path = Path(tempfile.gettempdir()) / f"transit_scraper_{os.getpid()}_{uuid.uuid4().hex}.json"
    process = context.Process(
        target=_scrape_agency_process_worker,
        args=(agency, str(result_path)),
        daemon=True,
    )
    process.start()
    process.join(timeout)

    if process.is_alive():
        _stop_process_tree(process)
        result_path.unlink(missing_ok=True)
        return {
            "agency": agency["agency"],
            "platform": agency["platform"],
            "jobs": [],
            "elapsed": time.perf_counter() - started_at,
            "error": f"Timed out after {timeout}s in isolated scraper worker",
        }

    if not result_path.exists():
        exit_code = process.exitcode
        result_path.unlink(missing_ok=True)
        return {
            "agency": agency["agency"],
            "platform": agency["platform"],
            "jobs": [],
            "elapsed": time.perf_counter() - started_at,
            "error": f"Isolated scraper worker exited without a result (exit code {exit_code})",
        }

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    finally:
        result_path.unlink(missing_ok=True)

    result["elapsed"] = time.perf_counter() - started_at
    return result


def _print_scrape_result(result: dict) -> None:
    agency = result["agency"]
    platform = result["platform"]
    elapsed = result["elapsed"]
    if result["error"]:
        print(f"Skipped {agency} ({platform}) in {elapsed:.1f}s: {result['error']}", flush=True)
        return
    print(f"Found {len(result['jobs'])} jobs for {agency} ({platform}) in {elapsed:.1f}s", flush=True)


def run_all_scrapers() -> list[dict]:
    all_jobs = []
    force_sequential = os.getenv("SCRAPER_MODE", "").lower() == "sequential"

    if force_sequential:
        print(f"Scraping {len(AGENCIES)} agencies sequentially", flush=True)
        for agency in AGENCIES:
            result = _scrape_agency(agency)
            all_jobs.extend(result["jobs"])
            _print_scrape_result(result)
        return all_jobs

    governmentjobs_agencies = [agency for agency in AGENCIES if agency["platform"] == "governmentjobs"]
    parallel_agencies = [
        agency
        for agency in AGENCIES
        if agency["platform"] in PARALLEL_PLATFORMS and agency["platform"] != "governmentjobs"
    ]
    serial_agencies = [agency for agency in AGENCIES if agency["platform"] in SERIAL_PLATFORMS]
    browser_agencies = [
        agency
        for agency in AGENCIES
        if agency["platform"] not in PARALLEL_PLATFORMS and agency["platform"] not in SERIAL_PLATFORMS
    ]

    if parallel_agencies and not force_sequential:
        workers = min(DEFAULT_SCRAPER_WORKERS, len(parallel_agencies))
        print(f"Scraping {len(parallel_agencies)} HTTP/API agencies with {workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_scrape_agency, agency): agency for agency in parallel_agencies}
            for future in as_completed(futures):
                result = future.result()
                all_jobs.extend(result["jobs"])
                _print_scrape_result(result)

    if governmentjobs_agencies and not force_sequential:
        workers = min(DEFAULT_GOVJOBS_AGENCY_WORKERS, len(governmentjobs_agencies))
        print(f"Scraping {len(governmentjobs_agencies)} GovernmentJobs agencies with {workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_scrape_agency, agency): agency for agency in governmentjobs_agencies}
            for future in as_completed(futures):
                result = future.result()
                all_jobs.extend(result["jobs"])
                _print_scrape_result(result)

    if serial_agencies:
        print(f"Scraping {len(serial_agencies)} serial browser/custom agencies in isolated workers", flush=True)
        for agency in serial_agencies:
            result = _scrape_agency_isolated(agency)
            all_jobs.extend(result["jobs"])
            _print_scrape_result(result)

    if browser_agencies:
        print(
            f"Scraping {len(browser_agencies)} browser/custom agencies in isolated workers",
            flush=True,
        )
        for agency in browser_agencies:
            result = _scrape_agency_isolated(agency)
            all_jobs.extend(result["jobs"])
            _print_scrape_result(result)

    return all_jobs


if __name__ == "__main__":
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    jobs = run_all_scrapers()
    df = pd.DataFrame(jobs)

    if df.empty:
        print("\nNo jobs were collected. Some sites may block scraping or require custom parsers.")
    else:
        df = df.drop_duplicates(subset=["job_id"])
        sort_cols = [
            col
            for col in ["agency", "ai_sort_category", "ai_sort_seniority", "category", "title"]
            if col in df.columns
        ]
        df = df.sort_values(sort_cols).reset_index(drop=True)

    output_path = output_dir / "transit_jobs.csv"
    df.to_csv(output_path, index=False)
    write_site_data(df, Path("site"))

    print(f"\nSaved {len(df)} jobs to {output_path}")

    if not df.empty:
        print("\nPreview:")
        preview_cols = ["agency", "title", "category", "salary_text", "source_url"]
        print(df[preview_cols].head(20).to_string(index=False))
