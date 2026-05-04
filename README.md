# Transit Job Scraper

A local Python project for collecting public transportation job postings from major U.S. transit agencies and viewing them in a lightweight job-search website.

The core idea is simple: transit agencies use different career platforms, so each agency is mapped to a platform-specific scraper, then normalized into one shared dataset for job seekers.

## What It Does

- Scrapes jobs from major U.S. public transportation agencies
- Normalizes titles, agencies, locations, categories, seniority, dates, and pay
- Parses salary ranges into clear `salary_min`, `salary_max`, and `salary_range_display` fields
- Keeps original salary text for source accuracy
- Writes a CSV dataset to `output/transit_jobs.csv`
- Writes a local website data bundle to `site/data.js`
- Provides a static job explorer at `site/index.html`

The website supports search, agency/category/seniority filters, minimum pay filtering, and sorting by newest posted, closing soon, pay, agency, or title.

## Agencies

Current configured agencies include:

- MTA
- LA Metro
- CTA
- NJ Transit
- SFMTA
- WMATA
- SEPTA
- MBTA
- King County Metro
- RTC Transit
- BART
- TriMet
- Honolulu DTS
- AC Transit
- RTD Denver
- MARTA
- Sound Transit

Agency configuration lives in `agencies.py`.

## Scraper Platforms

Implemented platform scrapers:

- `governmentjobs` - GovernmentJobs / NEOGOV endpoint and detail pages
- `mta_custom` - MTA custom career site with browser fallback and detail cache
- `taleo` - Taleo jobboard API, used for CTA
- `successfactors` - SEPTA
- `workday` - RTD Denver
- `oracle` - MARTA
- `ukg` - Sound Transit
- `salesforce_custom` - NJ Transit
- `sf_careers` - SFMTA / City and County of San Francisco careers
- `peoplesoft_wmata` - WMATA PeopleSoft listings

## Install

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For the MTA browser fallback, Playwright/Chromium must also be available in the environment.

## Run

```bash
python main.py
```

Outputs:

```text
output/transit_jobs.csv
site/data.js
```

Open the local website:

```text
site/index.html
```

## Salary Data

Salary handling prioritizes precision for job seekers:

- Original source salary text is preserved in `salary_text`
- Parsed ranges are stored as `salary_min` and `salary_max`
- Display-ready ranges are stored as `salary_range_display`
- Hourly and annual pay are labeled with `salary_unit`
- Annual comparison fields are generated only when safe to compare
- The website does not show manually calculated midpoint salary

If a job does not list pay, the site shows `Salary not listed`.

## MTA Detail Cache

MTA detail pages are slow because the site often requires browser fallback. To avoid reopening every detail page on each run, the MTA scraper reads existing MTA jobs from:

```text
output/transit_jobs.csv
```

During browser fallback, it still scans the current MTA listing pages to find open jobs, but it reuses cached detail data for any MTA job URL already present in the dataset. Only new MTA job URLs need detail-page enrichment.

## Project Structure

```text
transit_job_scraper/
├── agencies.py
├── main.py
├── normalizer.py
├── requirements.txt
├── README.md
├── output/
│   └── transit_jobs.csv
├── scrapers/
│   ├── __init__.py
│   ├── governmentjobs.py
│   ├── mta_custom.py
│   ├── oracle.py
│   ├── peoplesoft_wmata.py
│   ├── salesforce_custom.py
│   ├── sf_careers.py
│   ├── successfactors.py
│   ├── taleo.py
│   ├── ukg.py
│   └── workday.py
└── site/
    ├── app.js
    ├── data.js
    ├── index.html
    └── styles.css
```

## Notes

Career portals change frequently. Some agencies may return fewer jobs than expected, block scraping, or require a scraper update when their platform changes. The runner logs each agency result and continues if one agency fails.
