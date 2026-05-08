from pathlib import Path
import json

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
    scrape_cdta_custom,
    scrape_dayforce,
    scrape_icims,
    scrape_munis_selfservice,
    scrape_nfta_custom,
    scrape_norta_custom,
    scrape_prt_custom,
    scrape_static_job_links,
    scrape_taleo_v2,
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
    "careersingovernment": scrape_static_job_links,
    "charlotte_custom": scrape_static_job_links,
    "dayforce": scrape_dayforce,
    "detroit_custom": scrape_static_job_links,
    "foothill_custom": scrape_static_job_links,
    "grtc_custom": scrape_static_job_links,
    "madison_custom": scrape_static_job_links,
    "metra_custom": scrape_cadient,
    "icims": scrape_icims,
    "munis_selfservice": scrape_munis_selfservice,
    "nfta_custom": scrape_nfta_custom,
    "norta_custom": scrape_norta_custom,
    "oracle_legacy": scrape_static_job_links,
    "panynj_custom": scrape_static_job_links,
    "peoplesoft_miami": scrape_static_job_links,
    "prt_custom": scrape_prt_custom,
    "rta_new_orleans_custom": scrape_norta_custom,
    "sorta_custom": scrape_static_job_links,
    "static_job_links": scrape_static_job_links,
    "taleo_v2": scrape_taleo_v2,
    "transdev": scrape_static_job_links,
    "uta_custom": scrape_static_job_links,
    "via_custom": scrape_static_job_links,
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


def run_all_scrapers() -> list[dict]:
    all_jobs = []

    for agency in AGENCIES:
        platform = agency["platform"]
        scraper = SCRAPER_MAP.get(platform)

        if scraper is None:
            print(f"No scraper found for {agency['agency']} / {platform}")
            continue

        print(f"\nScraping {agency['agency']} using {platform} scraper")

        try:
            jobs = scraper(agency)
            all_jobs.extend(jobs)
            print(f"Found {len(jobs)} jobs")
        except Exception as exc:
            print(f"Skipped {agency['agency']}: {exc}")

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
