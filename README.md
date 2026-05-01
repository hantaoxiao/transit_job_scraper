# Transit Job Scraper MVP

This is a beginner-friendly local Python starter project for collecting public transportation job postings from major U.S. transit agencies.

The project is designed around one important idea:

> Different transit agencies use different career platforms, so the scraper first classifies agencies by platform type, then routes each agency to the correct scraper.

## Current status

Implemented:
- Agency classification
- Standardized job output format
- Reusable GovernmentJobs / NEOGOV scraper starter
- Placeholder scrapers for Workday, Oracle, Taleo, SuccessFactors, MTA custom, UKG, and Salesforce custom
- CSV output

The first practical target is to collect jobs from GovernmentJobs-based agencies such as:
- LA Metro
- BART
- MBTA
- TriMet

Other platforms need custom work later.

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
