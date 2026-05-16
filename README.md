# Transit Job Scraper

A local Python project for collecting public transportation job postings from major U.S. transit agencies and viewing them in a lightweight job-search website.

The core idea is simple: transit agencies use many different career platforms, so each agency is mapped to a platform-specific scraper, then normalized into one shared dataset for job seekers.

## What It Does

- Scrapes jobs from 119 U.S. public transportation agencies
- Normalizes titles, agencies, `City, State` locations, categories, seniority, dates, and pay
- Parses salary ranges into clear `salary_min`, `salary_max`, and `salary_range_display` fields
- Preserves original salary text for source accuracy
- Writes a CSV dataset to `output/transit_jobs.csv`
- Writes a local website data bundle to `site/data.js`
- Provides a static job explorer at `site/index.html`

The website is designed for job hunting. It supports keyword search, agency/state/category/seniority/schedule filters, minimum pay filtering, list or map view, pagination, official agency logos, and sorting by newest posted, closing soon, pay, agency, or title.

The scraper runner is optimized for repeat full refreshes:

- HTTP/API-based scrapers run concurrently by default
- Browser-heavy and custom rendered scrapers run one agency at a time by default, with MTA kept serial for its challenge/cache flow
- Large detail-page loops are fetched concurrently within each agency where the source supports it
- Each agency log line includes elapsed time, making slow portals easy to spot

## Agencies

Agency configuration lives in `agencies.py`. Current configured agencies:

The California expansion uses the 2024 agency workbook as the source list and adds the California Full Reporter agencies with reporter acronyms first. Some of these agencies have no open jobs today, but their career pages are still configured so future openings can be collected.

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
- Access Services (El Monte, CA)
- CalVans (Visalia, CA)
- MTC (San Francisco, CA)
- SJCOG (Stockton, CA)
- SANDAG (San Diego, CA)
- LADOT (Los Angeles, CA)
- SamTrans (San Carlos, CA)
- Victor Valley Transit Authority (Hesperia, CA)
- Long Beach Transit (Long Beach, CA)
- North County Transit District (Oceanside, CA)
- Monterey-Salinas Transit (Monterey, CA)
- Big Blue Bus (Santa Monica, CA)
- Fresno Area Express (Fresno, CA)
- County Connection (Concord, CA)
- San Joaquin RTD (Stockton, CA)
- StanisCruise (Modesto, CA)
- Santa Cruz METRO (Santa Cruz, CA)
- Golden Empire Transit District (Bakersfield, CA)
- Antelope Valley Transit Authority (Lancaster, CA)
- Santa Clarita Transit (Santa Clarita, CA)
- Montebello Bus Lines (Montebello, CA)
- SBCTA (San Bernardino, CA)
- Torrance Transit (Torrance, CA)
- Gold Coast Transit District (Oxnard, CA)
- Golden Gate Transit (San Francisco, CA)
- Marin Transit (San Rafael, CA)
- Santa Barbara MTD (Santa Barbara, CA)
- Kings Area Regional Transit (Hanford, CA)
- Anaheim Regional Transportation (Anaheim, CA)
- Sonoma County Transit (Santa Rosa, CA)
- LAVTA (Livermore, CA)
- Napa Valley Transportation Authority (Napa, CA)
- Tulare County Regional Transit Agency (Visalia, CA)
- YoloTD (Woodland, CA)
- Placer County Transit/TART (Auburn, CA)
- Pomona Valley Transportation Authority (La Verne, CA)
- VCTC (Camarillo, CA)
- Kern Regional Transit (Bakersfield, CA)
- SLO RTA (San Luis Obispo, CA)
- ICTC (El Centro, CA)
- RCTC (Riverside, CA)
- Visalia Transit (Visalia, CA)
- Butte Regional Transit/B-Line (Chico, CA)
- WestCAT (Pinole, CA)
- Unitrans (Davis, CA)
- Altamont Corridor Express (Stockton, CA)
- Norwalk Transit (Norwalk, CA)
- Santa Maria Regional Transit (Santa Maria, CA)
- Beach Cities Transit (Redondo Beach, CA)
- Commerce Transit (Commerce, CA)
- San Francisco Bay Ferry (San Francisco, CA)
- Clean Air Express (Santa Barbara, CA)
- La Mirada Transit (La Mirada, CA)

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
- `adp` - ADP WorkForce Now API plus rendered fallback for newer boards
- `applicantpro` - ApplicantPro listings with JSON-LD detail extraction
- `dayforce` - Dayforce search/detail APIs with rendered fallback
- `transdev` - Transdev/NICE job pages through lightweight listing and detail reads
- `static_job_links` - Conservative static-link scraper for simpler career pages
- `static_text` - Conservative text-section scraper for official agency pages that list openings directly
- `calopps` - CalOpps agency pages, used by some California transit agencies
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
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
python main.py
```

Optional performance controls:

```bash
SCRAPER_WORKERS=6 GOVJOBS_DETAIL_WORKERS=4 python main.py
WORKDAY_DETAIL_WORKERS=8 UKG_DETAIL_WORKERS=8 JOBS2WEB_DETAIL_WORKERS=8 python main.py
RISKY_SCRAPER_TIMEOUT=180 python main.py
SCRAPER_MODE=sequential python main.py
```

`SCRAPER_WORKERS` controls HTTP/API agency parallelism. Browser/custom agencies run in isolated child processes with per-agency timeouts, so a crashing Playwright portal cannot stop the full refresh. `RISKY_SCRAPER_TIMEOUT` controls the default timeout for those isolated scrapers; platform-specific timeouts in `main.py` override it for known long-running boards. Detail worker settings speed up salary/detail collection inside large API boards without skipping detail pages. Use `SCRAPER_MODE=sequential` when debugging a single platform or comparing behavior with the older serial runner.

The slowest rendered boards are optimized to avoid browser detail loops where possible. ADP WorkForce Now, Dayforce, ApplicantPro, Transdev/NICE, and VIA detail pages use API, JSON-LD, or lightweight HTML/JSON reads first; Playwright remains as a fallback for portals that do not expose stable detail data.

San Diego MTS is currently marked with `skip_scrape_reason` because its ADP rendered board crashes Playwright during full refreshes. Keep it skipped until the ADP scraper is replaced with a safer non-browser parser.

## Public Deployment

The repository includes `.github/workflows/scrape-and-deploy.yml` for GitHub Pages. It can be run manually from the Actions tab and is scheduled for every 2 hours on weekdays from 7 AM through 7 PM Eastern time.

The workflow installs dependencies, installs Playwright Chromium, restores the previous `output/transit_jobs.csv` cache, runs `python main.py`, uploads the latest CSV as a short-lived artifact, saves the CSV cache for the next scheduled run, and deploys the generated `site/` folder to GitHub Pages. Enable Pages with source set to GitHub Actions in the repository settings before relying on the scheduled deployment.

In CI, MTA first tries direct requests. If the MTA site blocks GitHub Actions, the scraper uses a live text-rendered MTA listing fallback so the open job list stays current, enriches new MTA jobs from live detail pages, and reuses cached detail fields only for still-open jobs it has already seen.

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
