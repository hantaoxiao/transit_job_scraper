# Transit Job Scraper MVP

This is a beginner-friendly local Python starter project for collecting public transportation job postings from major U.S. transit agencies.

The project is designed around one important idea:

> Different transit agencies use different career platforms, so the scraper first classifies agencies by platform type, then routes each agency to the correct scraper.

## Current status

Implemented:
- Agency classification
- Standardized job output format
- Reusable GovernmentJobs / NEOGOV scraper starter
- Scrapers for MTA custom, SuccessFactors, Workday, Oracle, UKG, NJ Transit Salesforce, SF Careers, and WMATA PeopleSoft pages
- GovernmentJobs / NEOGOV scraper using the platform's job-results endpoint and detail pages
- CSV output

Some career portals return zero public jobs at times or require browser/API behavior that changes by agency. The script logs each agency result and continues when one site fails.

## Install

From this folder, run:

```bash
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows PowerShell

pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The script will save output to:

```text
output/transit_jobs.csv
```

The script also writes a local website data bundle to:

```text
site/data.js
```

Open this file in a browser to view the job explorer:

```text
site/index.html
```

Salary fields keep the original source text and add normalized range fields such as `salary_min`, `salary_max`, `salary_range_display`, and annualized comparison fields when the salary is safe to compare.

## Project structure

```text
transit_job_scraper/
├── main.py
├── agencies.py
├── normalizer.py
├── requirements.txt
├── README.md
├── scrapers/
│   ├── __init__.py
│   ├── governmentjobs.py
│   ├── peoplesoft_wmata.py
│   ├── sf_careers.py
│   ├── workday.py
│   ├── oracle.py
│   ├── taleo.py
│   ├── successfactors.py
│   ├── mta_custom.py
│   ├── ukg.py
│   └── salesforce_custom.py
└── output/
```

## Notes

Many career portals are JavaScript-heavy. For those, basic `requests` may not be enough. The next improvement would be adding Playwright for rendered HTML scraping or finding each portal's internal API.
