# Transit Job Scraper

A local Python project for collecting public transportation job postings from major U.S. transit agencies and viewing them in a lightweight job-search website.

The core idea is simple: transit agencies use many different career platforms, so each agency is mapped to a platform-specific scraper, then normalized into one shared dataset for job seekers.

## What It Does

- Scrapes jobs from 66 major U.S. public transportation agencies
- Normalizes titles, agencies, `City, State` locations, categories, seniority, dates, and pay
- Parses salary ranges into clear `salary_min`, `salary_max`, and `salary_range_display` fields
- Preserves original salary text for source accuracy
- Writes a CSV dataset to `output/transit_jobs.csv`
- Writes a local website data bundle to `site/data.js`
- Provides a static job explorer at `site/index.html`

The website is designed for job hunting. It supports keyword search, agency/state/category/seniority/schedule filters, minimum pay filtering, list or map view, pagination, official agency logos, and sorting by newest posted, closing soon, pay, agency, or title.

## Agencies

Agency configuration lives in `agencies.py`. Current configured agencies:

- MTA (New York, NY)
- LA Metro (Los Angeles, CA)
- CTA (Chicago, IL)
- NJ Transit (Newark, NJ)
- SFMTA (San Francisco, CA)
- WMATA (Washington, DC)
- SEPTA (Philadelphia, PA)
- MBTA (Boston, MA)
- King County Metro (Seattle, WA)
- RTC Transit (Las Vegas, NV)
- BART (Oakland, CA)
- TriMet (Portland, OR)
- Honolulu DTS (Honolulu, HI)
- AC Transit (Oakland, CA)
- RTD Denver (Denver, CO)
- MARTA (Atlanta, GA)
- Sound Transit (Seattle, WA)
- Houston METRO (Houston, TX)
- Miami-Dade DTPW (Miami, FL)
- DART (Dallas, TX)
- San Diego MTS (San Diego, CA)
- Utah Transit Authority (Salt Lake City, UT)
- OCTA (Orange, CA)
- Valley Metro (Phoenix, AZ)
- VTA (San Jose, CA)
- Metro Transit MN (Minneapolis, MN)
- Pace (Arlington Heights, IL)
- Metra (Chicago, IL)
- Metrolink (Los Angeles, CA)
- Pittsburgh Regional Transit (Pittsburgh, PA)
- VIA Metropolitan Transit (San Antonio, TX)
- SacRT (Sacramento, CA)
- LYNX (Orlando, FL)
- Palm Tran (West Palm Beach, FL)
- NICE Bus (Mineola, NY)
- SMART (Detroit, MI)
- Foothill Transit (West Covina, CA)
- COTA (Columbus, OH)
- GCRTA (Cleveland, OH)
- IndyGo (Indianapolis, IN)
- MCTS (Milwaukee, WI)
- Hampton Roads Transit (Norfolk, VA)
- KCATA (Kansas City, MO)
- CATS (Charlotte, NC)
- CapMetro (Austin, TX)
- GRTC (Richmond, VA)
- RTA New Orleans (New Orleans, LA)
- Metro Transit Madison (Madison, WI)
- DDOT (Detroit, MI)
- SORTA Metro (Cincinnati, OH)
- PATH (Jersey City, NJ)
- Caltrain (San Carlos, CA)
- Broward County Transit (Fort Lauderdale, FL)
- HART (Tampa, FL)
- PSTA (St. Petersburg, FL)
- Sun Tran (Tucson, AZ)
- Omnitrans (San Bernardino, CA)
- Riverside Transit Agency (Riverside, CA)
- CDTA (Albany, NY)
- NFTA (Buffalo, NY)
- Community Transit (Everett, WA)
- Spokane Transit Authority (Spokane, WA)
- Ben Franklin Transit (Richland, WA)
- Intercity Transit (Olympia, WA)
- Kitsap Transit (Bremerton, WA)
- Everett Transit (Everett, WA)

## Scraper Platforms

Implemented platform scrapers:

- `governmentjobs` - GovernmentJobs / NEOGOV endpoint and detail pages
- `mta_custom` - MTA custom career site with browser fallback and detail cache
- `taleo` - Taleo jobboard API, used for CTA
- `taleo_v2` - Rendered Taleo v2 boards, used for PSTA
- `successfactors` - SEPTA
- `workday` - Workday and newer `myworkdaysite.com/recruiting/...` paths, including OCTA
- `oracle` - Oracle Cloud HCM candidate sites
- `ukg` - UKG / UltiPro job boards
- `salesforce_custom` - NJ Transit Salesforce career site
- `sf_careers` - SFMTA / City and County of San Francisco careers
- `peoplesoft_wmata` - WMATA PeopleSoft listings
- `jobs2web` - Jobs2Web / SAP-style boards, used for Houston METRO
- `jobvite` - Jobvite boards, used for PATH / PANYNJ
- `cadient` - Cadient boards, used for Metra
- `adp` - ADP rendered job boards
- `applicantpro` - ApplicantPro rendered listings
- `dayforce` - Dayforce rendered candidate portals
- `static_job_links` - Conservative static-link scraper for simpler career pages
- `prt_custom` - Pittsburgh Regional Transit custom listing page
- `norta_custom` - RTA New Orleans custom listing page
- `cdta_custom` - CDTA custom employment pages
- `nfta_custom` - NFTA custom job posting pages
- `icims` - iCIMS career portals, used for Community Transit
- `munis_selfservice` - Munis Self Service job boards, used for Spokane Transit Authority

## Install

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Some rendered career boards use Playwright. If browser fallback is needed:

```bash
playwright install chromium
```

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

Because the website is static, opening `site/index.html` directly in a browser is enough after `site/data.js` has been generated.

## Website Features

- Search supports exact keyword matches plus practical related terms for common job families such as analyst, planner, operator, mechanic, and engineer
- Filters include agency, state, category, seniority, schedule, and minimum pay
- Schedule filtering separates full-time and part-time while treating common permanent/regular terms as full-time
- List view is paginated, with 10 jobs shown by default
- Map view groups filtered jobs by agency/location
- Official agency logos are displayed in job cards when local assets are available

Logo metadata lives in `site/app.js`, and logo files live in `site/assets/agency-logos/`. The helper script `tools/fetch_agency_logos.py` can refresh logo assets from Wikimedia/direct URLs/official-site favicon sources.

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
│   ├── browser_jobboard.py
│   ├── cadient.py
│   ├── governmentjobs.py
│   ├── jobvite.py
│   ├── jobs2web.py
│   ├── mta_custom.py
│   ├── oracle.py
│   ├── peoplesoft_wmata.py
│   ├── salesforce_custom.py
│   ├── sf_careers.py
│   ├── successfactors.py
│   ├── taleo.py
│   ├── ukg.py
│   └── workday.py
├── site/
│   ├── app.js
│   ├── data.js
│   ├── index.html
│   ├── styles.css
│   └── assets/
│       └── agency-logos/
└── tools/
    └── fetch_agency_logos.py
```

## Notes

Career portals change frequently. Some agencies may return fewer jobs than expected, block scraping, or require a scraper update when their platform changes. The runner logs each agency result and continues if one agency fails.
