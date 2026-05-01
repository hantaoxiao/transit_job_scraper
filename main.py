from pathlib import Path

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


SCRAPER_MAP = {
    "governmentjobs": scrape_governmentjobs,
    "workday": scrape_workday,
    "oracle": scrape_oracle,
    "taleo": scrape_taleo,
    "successfactors": scrape_successfactors,
    "mta_custom": scrape_mta,
    "ukg": scrape_ukg,
    "salesforce_custom": scrape_salesforce_custom,
}

UNIMPLEMENTED_PLATFORMS = {
    "oracle",
    "salesforce_custom",
    "taleo",
    "ukg",
    "workday",
}


def run_all_scrapers() -> list[dict]:
    all_jobs = []

    for agency in AGENCIES:
        platform = agency["platform"]
        scraper = SCRAPER_MAP.get(platform)

        if scraper is None:
            print(f"No scraper found for {agency['agency']} / {platform}")
            continue

        print(f"\nScraping {agency['agency']} using {platform} scraper")

        if platform in UNIMPLEMENTED_PLATFORMS:
            print(f"Skipped: {platform} scraper is not implemented yet")
            continue

        try:
            jobs = scraper(agency)
            all_jobs.extend(jobs)
            print(f"Found {len(jobs)} jobs")
        except Exception as exc:
            print(f"Failed to scrape {agency['agency']} ({agency['jobs_url']}): {type(exc).__name__}: {exc}")

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
        df = df.sort_values(["agency", "title"]).reset_index(drop=True)

    output_path = output_dir / "transit_jobs.csv"
    df.to_csv(output_path, index=False)

    print(f"\nSaved {len(df)} jobs to {output_path}")

    if not df.empty:
        print("\nPreview:")
        preview_cols = ["agency", "title", "category", "salary_text", "source_url"]
        print(df[preview_cols].head(20).to_string(index=False))
