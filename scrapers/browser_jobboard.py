from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

    class PlaywrightError(Exception):
        pass

from normalizer import clean_text, extract_salary, normalize_job
from scrapers.detail_cache import cached_detail_text, cached_job, has_cached_detail


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


PLAYWRIGHT_INSTALL_MESSAGE = (
    "Playwright is not installed. Run: pip install -r requirements.txt; playwright install chromium"
)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


JINA_DETAIL_WORKERS = _env_int("JINA_DETAIL_WORKERS", 8)
CDTA_DETAIL_WORKERS = _env_int("CDTA_DETAIL_WORKERS", 6)
NFTA_DETAIL_WORKERS = _env_int("NFTA_DETAIL_WORKERS", 8)
STATIC_DETAIL_WORKERS = _env_int("STATIC_DETAIL_WORKERS", 4)


def _sync_playwright():
    if sync_playwright is None:
        raise RuntimeError(PLAYWRIGHT_INSTALL_MESSAGE)
    return sync_playwright()


def _detail_text(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(response.text, "lxml")
    return clean_text(soup.get_text(" ", strip=True))


def _detail_html(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return response.text


def _strip_html(value: str) -> str:
    if not value:
        return ""
    value = str(value)
    if "<" not in value and ">" not in value:
        return clean_text(value)
    return clean_text(BeautifulSoup(value, "lxml").get_text(" ", strip=True))


def _render_page(url: str, wait_ms: int = 8000) -> tuple[str, list[tuple[str, str]]]:
    body_text = ""
    links = []
    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(wait_ms)
            body_text = page.locator("body").inner_text(timeout=5000)
            for index in range(min(page.locator("a").count(), 500)):
                link = page.locator("a").nth(index)
                text = clean_text(link.inner_text(timeout=500))
                href = link.get_attribute("href") or ""
                if text or href:
                    links.append((text, urljoin(url, href)))
            browser.close()
    except PlaywrightError:
        return "", []
    return body_text, links


def _render_many_pages(urls: list[str], wait_ms: int = 8000, workers: int | None = None) -> dict[str, str]:
    unique_urls = list(dict.fromkeys(url for url in urls if url))
    if not unique_urls:
        return {}

    details = {}
    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            for url in unique_urls:
                page = browser.new_page(viewport={"width": 1366, "height": 1200})
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(wait_ms)
                    details[url] = clean_text(page.locator("body").inner_text(timeout=5000))
                except PlaywrightError:
                    details[url] = ""
                finally:
                    page.close()
            browser.close()
    except PlaywrightError:
        return details

    return details


def _jina_markdown(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        target = f"{parsed.netloc}{parsed.path}"
        if parsed.query:
            target += f"?{parsed.query}"
        candidates = [f"https://r.jina.ai/http://{target}", f"https://r.jina.ai/http://{url}"]
    else:
        candidates = [f"https://r.jina.ai/http://{url}"]

    best = ""
    for candidate in dict.fromkeys(candidates):
        try:
            response = requests.get(candidate, headers=HEADERS, timeout=45)
            response.raise_for_status()
        except requests.RequestException:
            continue
        text = response.text
        if len(text) > len(best):
            best = text
        if "Performing security verification" not in text and len(text) > 1000:
            return text
    return best


def _markdown_to_text(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return clean_text(re.sub(r"[*_#>`]+", " ", text))


def _markdown_label_value(block: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}:\s*(.+?)\s*$", block)
    return clean_text(match.group(1)) if match else ""


def _city_state_from_location(location: str, agency: dict) -> tuple[str, str]:
    parts = [part.strip() for part in clean_text(location).split(",") if part.strip()]
    if len(parts) >= 2:
        state = parts[-1].split()[0]
        if re.fullmatch(r"[A-Z]{2}", state):
            return parts[-2], state
    return agency["city"], agency["state"]


def _adp_detail_texts(url: str, titles: list[str]) -> dict[str, dict[str, str]]:
    unique_titles = list(dict.fromkeys(title for title in titles if title))
    if not unique_titles:
        return {}

    details = {}
    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            for title in unique_titles:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(7000)
                try:
                    page.get_by_text(title, exact=True).first.click(timeout=5000)
                except PlaywrightError:
                    try:
                        page.get_by_text(title).first.click(timeout=5000)
                    except PlaywrightError:
                        continue
                page.wait_for_timeout(3500)
                details[title] = {
                    "text": clean_text(page.locator("body").inner_text(timeout=5000)),
                    "url": page.url,
                }
            browser.close()
    except PlaywrightError:
        return {}

    return details


def _adp_wfn_cid(url: str) -> str:
    parsed = urlparse(url)
    cid = parse_qs(parsed.query).get("cid", [""])[0]
    if cid:
        return cid

    try:
        response = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return parse_qs(urlparse(response.url).query).get("cid", [""])[0]


def _adp_custom_string(item: dict, code: str) -> str:
    fields = item.get("customFieldGroup", {}).get("stringFields", [])
    for field in fields:
        if field.get("nameCode", {}).get("codeValue") == code:
            return clean_text(field.get("stringValue"))
    return ""


def _adp_salary_text(item: dict) -> str:
    salary_range = _adp_custom_string(item, "SalaryRange")
    if salary_range:
        match = re.match(
            r"(\d[\d,.]*)\s+To\s+(\d[\d,.]*)\s+\(([^)]+)\)\s+([A-Za-z]+)",
            salary_range,
            flags=re.IGNORECASE,
        )
        if match:
            low, high, currency, unit = match.groups()
            symbol = "$" if currency.upper() == "USD" else f"{currency} "
            return clean_text(f"{symbol}{low} - {symbol}{high} {unit}")
        return salary_range

    pay_range = item.get("payGradeRange") or {}
    low = (pay_range.get("minimumRate") or {}).get("amountValue")
    high = (pay_range.get("maximumRate") or {}).get("amountValue")
    if low is not None and high is not None:
        return clean_text(f"${float(low):,.2f} - ${float(high):,.2f}")
    return ""


def _adp_location(item: dict, agency: dict) -> tuple[str, str, str]:
    locations = item.get("requisitionLocations") or []
    if not locations:
        return agency["city"], agency["state"], ""
    location = locations[0]
    address = location.get("address") or {}
    city = clean_text(address.get("cityName")) or agency["city"]
    state = clean_text((address.get("countrySubdivisionLevel1") or {}).get("codeValue")) or agency["state"]
    label = clean_text((location.get("nameCode") or {}).get("shortName")) or clean_text(f"{city}, {state}")
    return city, state, label


def _scrape_adp_wfn_api(agency: dict) -> list[dict]:
    cid = _adp_wfn_cid(agency["jobs_url"])
    if not cid:
        return []

    api_url = "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions"
    params = {
        "cid": cid,
        "timeStamp": str(int(time.time() * 1000)),
        "ccId": "19000101_000001",
        "lang": "en_US",
        "locale": "en_US",
        "$top": "100",
    }
    try:
        response = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return []

    jobs = []
    for item in data.get("jobRequisitions", []):
        title = clean_text(item.get("requisitionTitle"))
        if not title:
            continue

        city, state, location = _adp_location(item, agency)
        salary_text = _adp_salary_text(item)
        employment_type = clean_text((item.get("workLevelCode") or {}).get("shortName"))
        req_id = clean_text(item.get("clientRequisitionID") or _adp_custom_string(item, "ExternalJobID") or item.get("itemID"))
        raw_context = clean_text(" ".join([title, req_id, location, employment_type, salary_text]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=agency["jobs_url"],
                platform=agency["platform"],
                salary_text=salary_text or extract_salary(raw_context),
                posted_date=clean_text(item.get("postDate")),
                description=raw_context,
                raw_context=raw_context,
                extra_fields={"requisition_id": req_id, "employment_type": employment_type},
            )
        )

    return jobs


def scrape_adp(agency: dict) -> list[dict]:
    api_jobs = _scrape_adp_wfn_api(agency)
    if api_jobs:
        return api_jobs

    body_text, _ = _render_page(agency["jobs_url"], wait_ms=10000)
    if agency["jobs_url"].rstrip("/").endswith("/job-listing") and not re.search(
        r"Recently Posted Jobs|Current Openings", body_text, flags=re.IGNORECASE
    ):
        fallback = dict(agency, jobs_url=agency["jobs_url"].rstrip("/").rsplit("/", 1)[0])
        return scrape_adp(fallback)
    match = re.search(
        r"Current Openings\s+\(\d+\s+of\s+\d+\)\s+Search\s+(.+?)\s+Stay connected with us",
        body_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return _scrape_adp_myjobs(agency, body_text)

    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    parsed_jobs = []
    index = 0
    while index + 1 < len(lines):
        title = clean_text(lines[index])
        location = clean_text(lines[index + 1])
        meta = clean_text(lines[index + 2]) if index + 2 < len(lines) else ""

        if not title or title.lower() in {"search", "actions"}:
            index += 1
            continue

        city, state = _city_state_from_location(location, agency)
        posted_date = ""
        employment_type = ""
        posted_match = re.search(r"(\bToday\b|\b\d+\s+days?\s+ago\b|\b30\+\s+days?\s+ago\b)", meta, flags=re.IGNORECASE)
        if posted_match:
            posted_date = posted_match.group(1)
            employment_type = clean_text(meta[posted_match.end() :])
        else:
            employment_type = meta

        parsed_jobs.append(
            {
                "title": title,
                "city": city,
                "state": state,
                "location": location,
                "meta": meta,
                "posted_date": posted_date,
                "employment_type": employment_type,
            }
        )
        index += 3

    detail_titles = []
    for job in parsed_jobs:
        listing_context = clean_text(" ".join([job["title"], job["location"], job["meta"]]))
        if not extract_salary(listing_context):
            detail_titles.append(job["title"])
    detail_texts = _adp_detail_texts(agency["jobs_url"], detail_titles) if detail_titles else {}
    jobs = []
    for item in parsed_jobs:
        detail = detail_texts.get(item["title"], {})
        description = detail.get("text", "")
        raw_context = clean_text(" ".join([item["title"], item["location"], item["meta"], description]))
        jobs.append(
            normalize_job(
                title=item["title"],
                agency=agency["agency"],
                city=item["city"],
                state=item["state"],
                source_url=detail.get("url") or agency["jobs_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                posted_date=item["posted_date"],
                description=description,
                raw_context=raw_context,
                extra_fields={"employment_type": item["employment_type"]},
            )
        )

    return jobs


def _scrape_adp_myjobs(agency: dict, body_text: str) -> list[dict]:
    match = re.search(r"Recently Posted Jobs\s+(.+?)\s+Show all", body_text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"Recently Posted Jobs\s+(.+?)\s+Talent Community", body_text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    if "Create Job Alert" in lines:
        lines = lines[lines.index("Create Job Alert") + 1 :]
    parsed_jobs = []
    index = 0
    while index + 3 < len(lines):
        title = clean_text(lines[index])
        location = clean_text(lines[index + 1])
        requisition_id = clean_text(lines[index + 2])
        if not title or title.lower() in {"create job alert"} or re.fullmatch(r"\d+[dhm]", title, flags=re.IGNORECASE):
            index += 1
            continue

        description_lines = []
        index += 3
        while index < len(lines) and lines[index].lower() != "apply":
            description_lines.append(lines[index])
            index += 1
        if index < len(lines) and lines[index].lower() == "apply":
            index += 1
        posted_date = ""
        if index < len(lines) and re.fullmatch(r"\d+[dhm]|today|yesterday", lines[index], flags=re.IGNORECASE):
            posted_date = lines[index]
            index += 1

        city, state = _city_state_from_location(location, agency)
        parsed_jobs.append(
            {
                "title": title,
                "city": city,
                "state": state,
                "location": location,
                "requisition_id": requisition_id,
                "posted_date": posted_date,
                "description": clean_text(" ".join(description_lines)),
            }
        )

    detail_titles = []
    for job in parsed_jobs:
        listing_context = clean_text(" ".join([job["title"], job["location"], job["requisition_id"], job["description"]]))
        if not extract_salary(listing_context):
            detail_titles.append(job["title"])
    detail_texts = _adp_detail_texts(agency["jobs_url"], detail_titles) if detail_titles else {}
    jobs = []
    for item in parsed_jobs:
        detail = detail_texts.get(item["title"], {})
        description = detail.get("text") or item["description"]
        raw_context = clean_text(" ".join([item["title"], item["location"], item["requisition_id"], description]))
        jobs.append(
            normalize_job(
                title=item["title"],
                agency=agency["agency"],
                city=item["city"],
                state=item["state"],
                source_url=detail.get("url") or agency["jobs_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                posted_date=item["posted_date"],
                description=description,
                raw_context=raw_context,
                extra_fields={"requisition_id": item["requisition_id"]},
            )
        )
    return jobs


def scrape_taleo_v2(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=10000)
    jobs = []
    seen_urls = set()
    view_links = [
        (clean_text(title), source_url)
        for title, source_url in links
        if "viewRequisition" in source_url and clean_text(title).lower() not in {"view", "apply"}
    ]

    for title, source_url in view_links:
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        detail_text = _detail_text(source_url)
        context_match = re.search(
            rf"{re.escape(title)}\s+(.+?)(?=\n[A-Z][^\n]+\n\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|PSTA is a dynamic|$)",
            body_text,
            flags=re.DOTALL,
        )
        listing_context = clean_text(context_match.group(1)) if context_match else ""
        combined = clean_text(" ".join([title, listing_context, detail_text]))
        closing_match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", listing_context)

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                closing_date=closing_match.group(1) if closing_match else "",
                description=detail_text,
                raw_context=combined,
            )
        )

    return jobs


def scrape_cdta_custom(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    entries = []
    seen_urls = set()

    for link in soup.select('a[href^="/employment/"]'):
        source_url = urljoin(agency["jobs_url"], link["href"])
        if source_url in seen_urls:
            continue
        if source_url.rstrip("/").endswith("/employment-opportunities"):
            continue
        seen_urls.add(source_url)

        cached = cached_job(agency["agency"], source_url=source_url, title=clean_text(link.get_text(" ", strip=True)))
        entries.append({"source_url": source_url, "cached": cached})

    details = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(CDTA_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_detail_html, entry["source_url"]): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                details[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        source_url = entry["source_url"]
        cached = entry["cached"]
        detail_html = details.get(source_url)
        if detail_html:
            detail_soup = BeautifulSoup(detail_html, "lxml")
            detail_text = clean_text(detail_soup.get_text(" ", strip=True))
        else:
            detail_text = cached_detail_text(cached)
            detail_soup = BeautifulSoup(detail_text, "lxml")
        title_node = detail_soup.select_one("h1")
        title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
        if not title and detail_soup.title:
            title = clean_text(detail_soup.title.get_text(" ", strip=True).split("|", 1)[0])
        title = title or cached.get("title", "")
        if not title or title.lower() in {"employment opportunities", "apply today"}:
            continue

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(detail_text) or cached.get("salary_text", ""),
                description=detail_text or cached.get("description", ""),
                raw_context=detail_text,
            )
        )

    return jobs


def scrape_nfta_custom(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    entries = []
    seen_urls = set()

    for link in soup.select('a[href*="job.aspx?id="]'):
        source_url = urljoin(agency["jobs_url"], link["href"])
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        title_hint = clean_text(link.get_text(" ", strip=True))
        cached = cached_job(agency["agency"], source_url=source_url, title=title_hint)
        entries.append({"source_url": source_url, "cached": cached})

    details = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(NFTA_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_detail_html, entry["source_url"]): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                details[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        source_url = entry["source_url"]
        cached = entry["cached"]
        detail_html = details.get(source_url)
        if detail_html:
            detail_soup = BeautifulSoup(detail_html, "lxml")
            detail_text = clean_text(detail_soup.get_text(" ", strip=True))
        else:
            detail_text = cached_detail_text(cached)
            detail_soup = BeautifulSoup(detail_text, "lxml")
        title_node = detail_soup.find("h2", class_=False) or detail_soup.find("h1")
        title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
        if not title and detail_soup.title:
            title = clean_text(detail_soup.title.get_text(" ", strip=True).replace("NFTA Job Detail:", ""))
        title = title or cached.get("title", "")
        if not title:
            continue

        posted_match = re.search(r"\bDate Posted:\s*([A-Za-z0-9/, ]+?)(?=\s+Deadline:)", detail_text, flags=re.IGNORECASE)
        closing_match = re.search(r"\bDeadline:\s*(.+?)(?=\s+Job Number:)", detail_text, flags=re.IGNORECASE)
        req_match = re.search(r"\bJob Number:\s*(.+?)(?=\s+Branch:)", detail_text, flags=re.IGNORECASE)

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(detail_text) or cached.get("salary_text", ""),
                posted_date=posted_match.group(1) if posted_match else cached.get("posted_date", ""),
                closing_date=closing_match.group(1) if closing_match else cached.get("closing_date", ""),
                description=detail_text or cached.get("description", ""),
                raw_context=detail_text,
                extra_fields={"requisition_id": req_match.group(1) if req_match else cached.get("requisition_id", "")},
            )
        )

    return jobs


def scrape_icims(agency: dict) -> list[dict]:
    iframe_url = agency["jobs_url"]
    if "in_iframe=1" not in iframe_url:
        separator = "&" if "?" in iframe_url else "?"
        iframe_url = f"{iframe_url}{separator}mobile=false&width=1010&height=500&bga=true&needsRedirect=false&jan1offset=-300&jun1offset=-240&in_iframe=1"

    response = requests.get(iframe_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        source_url = urljoin(iframe_url, link["href"]).replace("&amp;", "&")
        if not re.search(r"/jobs/\d+/.+/job", source_url):
            continue
        title = clean_text(link.get_text(" ", strip=True))
        title = re.sub(r"^Job Title\s+", "", title, flags=re.IGNORECASE).strip()
        if not title or title.lower() in {"more details", "view job"} or source_url in seen_urls:
            continue
        detail_url = source_url if "in_iframe=1" in source_url else f"{source_url}?in_iframe=1"
        source_url = re.sub(r"[?&]in_iframe=1", "", source_url)
        seen_urls.add(source_url)

        detail_text = _detail_text(detail_url)
        combined = clean_text(" ".join([title, detail_text]))
        salary_text = _icims_salary(detail_text) or extract_salary(combined)
        location_match = re.search(r"\b([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})\b", combined)
        city, state = _city_state_from_location(location_match.group(1) if location_match else "", agency)

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=salary_text,
                description=detail_text,
                raw_context=combined,
            )
        )

    return jobs


def _icims_salary(text: str) -> str:
    text = clean_text(text)
    unit = ""
    if re.search(r"\bAnnual\b", text, flags=re.IGNORECASE):
        unit = "Annually"
    elif re.search(r"\bHourly\b", text, flags=re.IGNORECASE):
        unit = "Hourly"

    min_match = re.search(r"\bMin(?:imum)?(?:\s+\([^)]*\))?(?:\s+\w+)?\s*(?:Range)?\s*USD\s*(\$\s*\d[\d,.]*)", text, flags=re.IGNORECASE)
    max_match = re.search(r"\bMax(?:imum)?(?:\s+\([^)]*\))?(?:\s+\w+)?\s*(?:Range)?\s*USD\s*(\$\s*\d[\d,.]*)", text, flags=re.IGNORECASE)
    if min_match and max_match:
        return clean_text(f"{min_match.group(1)} - {max_match.group(1)} {unit}")
    if min_match:
        return clean_text(f"{min_match.group(1)} {unit}")
    return ""


def scrape_munis_selfservice(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        source_url = urljoin(agency["jobs_url"], link["href"])
        if "JobDetail.aspx" not in source_url:
            continue
        title = clean_text(link.get_text(" ", strip=True))
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        detail_text = _detail_text(source_url)
        combined = clean_text(" ".join([title, detail_text]))
        jobs.append(
            normalize_job(
                title=title.title(),
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                description=detail_text,
                raw_context=combined,
            )
        )

    return jobs


def _dayforce_salary(detail_text: str) -> str:
    min_max = re.search(
        r"\bHiring\s+Min\s+Rate\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s+USD\s+"
        r"Hiring\s+Max\s+Rate\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)",
        detail_text,
        flags=re.IGNORECASE,
    )
    if min_max:
        return clean_text(f"${min_max.group(1)} - ${min_max.group(2)}")

    hourly = re.search(
        r"\bHourly\s+Pay\s+rate:\s*(\$\s*\d[\d,.]*)",
        detail_text,
        flags=re.IGNORECASE,
    )
    if hourly:
        return clean_text(hourly.group(1))

    return ""


def _dayforce_attribute_value(job: dict, *names: str):
    wanted = {name.lower() for name in names}
    for attribute in job.get("jobPostingAttributes") or []:
        if str(attribute.get("name", "")).lower() in wanted:
            return attribute.get("value")
    return None


def _dayforce_money(value, pay_type: str = "") -> str:
    if value in (None, ""):
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return clean_text(str(value))
    if pay_type.lower() == "hourly":
        return f"${amount:,.2f}"
    if amount.is_integer():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _dayforce_salary_from_attributes(job: dict) -> str:
    pay_type = clean_text(str(_dayforce_attribute_value(job, "PayType") or ""))
    unit = pay_type if pay_type else ""

    low = _dayforce_attribute_value(job, "HiringMinRate", "MinimumRate", "MinRate")
    high = _dayforce_attribute_value(job, "HiringMaxRate", "MaximumRate", "MaxRate")
    if low not in (None, "") and high not in (None, ""):
        return clean_text(f"{_dayforce_money(low, pay_type)} - {_dayforce_money(high, pay_type)} {unit}")

    rate = _dayforce_attribute_value(job, "HiringRate", "Rate", "PayRate")
    if rate not in (None, ""):
        return clean_text(f"{_dayforce_money(rate, pay_type)} {unit}")

    return ""


def _dayforce_content_text(job: dict) -> str:
    content = job.get("jobPostingContent") or {}
    return clean_text(
        " ".join(
            _strip_html(content.get(key))
            for key in ["jobDescriptionHeader", "jobDescription", "jobDescriptionFooter"]
            if content.get(key)
        )
    )


def _dayforce_next_build_id_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    script = soup.select_one("#__NEXT_DATA__")
    if not script:
        return ""
    try:
        data = json.loads(script.string or script.get_text())
    except ValueError:
        return ""
    return clean_text(data.get("buildId"))


def _dayforce_next_build_id(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    return _dayforce_next_build_id_from_html(response.text)


def _dayforce_detail_job(
    base: str,
    build_id: str,
    language: str,
    client_namespace: str,
    board_code: str,
    posting_id: str,
    session=None,
) -> dict:
    if not build_id or not posting_id:
        return {}

    detail_url = f"{base}/_next/data/{build_id}/{language}/{client_namespace}/{board_code}/jobs/{posting_id}.json"
    try:
        client = session or requests
        response = client.get(detail_url, headers={**HEADERS, "Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return {}
    return ((data.get("pageProps") or {}).get("jobData") or {}) if isinstance(data, dict) else {}


def _parse_dayforce_url(url: str) -> tuple[str, str, str, str]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3:
        return "en-US", "", "", parsed.scheme + "://" + parsed.netloc
    language, client_namespace, board_code = parts[:3]
    return language, client_namespace, board_code, parsed.scheme + "://" + parsed.netloc


def _dayforce_location(job: dict, agency: dict) -> tuple[str, str, str]:
    locations = job.get("postingLocations") or []
    if not locations:
        return agency["city"], agency["state"], ""
    location = locations[0]
    city = clean_text(location.get("cityName")) or agency["city"]
    state = clean_text(location.get("stateCode")) or agency["state"]
    label = clean_text(location.get("formattedAddress")) or clean_text(f"{city}, {state}")
    return city, state, label


def _dayforce_jobs_from_api(agency: dict) -> list[dict]:
    language, client_namespace, board_code, base = _parse_dayforce_url(agency["jobs_url"])
    if not client_namespace or not board_code:
        return []

    search_url = f"{base}/api/geo/{client_namespace}/jobposting/search"
    payload = {
        "clientNamespace": client_namespace,
        "jobBoardCode": board_code,
        "cultureCode": language,
        "distanceUnit": 0,
        "paginationStart": 0,
    }
    data = {}
    build_id = ""

    try:
        session = requests.Session()
        landing = session.get(agency["jobs_url"], headers=HEADERS, timeout=30)
        landing.raise_for_status()
        build_id = _dayforce_next_build_id_from_html(landing.text)
        csrf_cookie = unquote(session.cookies.get("__Host-next-auth.csrf-token", ""))
        csrf_token = csrf_cookie.split("|", 1)[0]
        if csrf_token:
            response = session.post(
                search_url,
                json=payload,
                headers={
                    **HEADERS,
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "x-csrf-token": csrf_token,
                    "referer": agency["jobs_url"],
                },
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
    except (requests.RequestException, ValueError):
        data = {}

    if not data:
        try:
            with _sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
                page = browser.new_page(viewport={"width": 1366, "height": 1200})
                csrf_token = ""

                def remember_token(request):
                    nonlocal csrf_token
                    if "/jobposting/search" in request.url:
                        csrf_token = request.headers.get("x-csrf-token") or csrf_token

                page.on("request", remember_token)
                try:
                    with page.expect_response(
                        lambda response: "/jobposting/search" in response.url,
                        timeout=15000,
                    ) as response_info:
                        page.goto(agency["jobs_url"], wait_until="domcontentloaded", timeout=30000)
                    data = response_info.value.json()
                except PlaywrightError:
                    page.goto(agency["jobs_url"], wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(6000)
                    if csrf_token:
                        response = page.request.post(
                            search_url,
                            data=payload,
                            headers={
                                "Accept": "application/json, text/plain, */*",
                                "Content-Type": "application/json",
                                "x-csrf-token": csrf_token,
                                "referer": agency["jobs_url"],
                            },
                        )
                        if response.status == 200:
                            data = response.json()
                browser.close()
        except PlaywrightError:
            return []

    if not build_id:
        build_id = _dayforce_next_build_id(agency["jobs_url"])
    postings = data.get("jobPostings", [])
    details_by_posting_id = {}
    if build_id and postings:
        workers = min(8, len(postings))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _dayforce_detail_job,
                    base,
                    build_id,
                    language,
                    client_namespace,
                    board_code,
                    clean_text(item.get("jobPostingId")),
                ): clean_text(item.get("jobPostingId"))
                for item in postings
                if clean_text(item.get("jobPostingId"))
            }
            for future in as_completed(futures):
                details_by_posting_id[futures[future]] = future.result()

    jobs = []
    for item in postings:
        title = clean_text(item.get("jobTitle"))
        posting_id = clean_text(item.get("jobPostingId"))
        if not title or not posting_id:
            continue
        detail = details_by_posting_id.get(posting_id, {})
        job_data = detail or item
        city, state, location = _dayforce_location(job_data, agency)
        description = _dayforce_content_text(detail) or _strip_html(item.get("jobDescription"))
        attribute_text = clean_text(
            " ".join(
                f"{attribute.get('name')} {attribute.get('value')}"
                for attribute in job_data.get("jobPostingAttributes") or []
                if attribute.get("name") and attribute.get("value") not in (None, "")
            )
        )
        raw_context = clean_text(
            " ".join([title, str(job_data.get("jobReqId") or item.get("jobReqId") or ""), location, attribute_text, description])
        )
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=f"{base}/{language}/{client_namespace}/{board_code}/jobs/{posting_id}",
                platform=agency["platform"],
                salary_text=_dayforce_salary_from_attributes(job_data)
                or _dayforce_salary(description)
                or extract_salary(raw_context),
                posted_date=clean_text(job_data.get("postingStartTimestampUTC") or item.get("postingStartTimestampUTC")),
                closing_date=clean_text(job_data.get("postingExpiryTimestampUTC") or item.get("postingExpiryTimestampUTC")),
                description=description,
                raw_context=raw_context,
                extra_fields={"requisition_id": clean_text(job_data.get("jobReqId") or item.get("jobReqId"))},
            )
        )
    return jobs


def scrape_dayforce(agency: dict) -> list[dict]:
    api_jobs = _dayforce_jobs_from_api(agency)
    if api_jobs:
        return api_jobs

    _, links = _render_page(agency["jobs_url"], wait_ms=10000)
    jobs = []
    seen_urls = set()
    job_links = []

    for title, source_url in links:
        if not title or title.lower() == "read more" or "/jobs/" not in source_url:
            continue
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        if source_url.startswith("https://dayforcehcm.com/"):
            source_url = source_url.replace("https://dayforcehcm.com/", "https://jobs.dayforcehcm.com/", 1)
        job_links.append((title, source_url))

    rendered_details = _render_many_pages([source_url for _, source_url in job_links], wait_ms=9000)
    for title, source_url in job_links:
        detail_text = rendered_details.get(source_url, "")
        if not detail_text:
            detail_text = _detail_text(source_url)
        location = ""
        location_match = re.search(r"\b([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})\b", detail_text)
        if location_match:
            location = location_match.group(1)
        city, state = _city_state_from_location(location, agency)
        raw_context = clean_text(" ".join([title, detail_text]))
        salary_text = _dayforce_salary(detail_text) or extract_salary(raw_context)

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=salary_text,
                description=detail_text,
                raw_context=raw_context,
            )
        )

    return jobs


def scrape_applicantpro(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=8000)
    jobs = []
    seen_urls = set()
    job_links = [(title, url) for title, url in links if re.search(r"/jobs/\d+", url)]
    pending = []

    for title, source_url in job_links:
        title = clean_text(title)
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        detail_text = _applicantpro_detail_text(source_url)
        if not detail_text:
            pending.append(source_url)
        jobs.append((title, source_url, detail_text))

    rendered_details = _render_many_pages(pending, wait_ms=8000) if pending else {}
    normalized_jobs = []
    for title, source_url, detail_text in jobs:
        if source_url in rendered_details and rendered_details[source_url]:
            detail_text = rendered_details[source_url]
        context_match = re.search(
            rf"{re.escape(title)}\s+(.+?)(?=\n[A-Z][^\n]+\n|Sign Up For Job Alerts|$)",
            body_text,
            flags=re.DOTALL,
        )
        listing_context = clean_text(context_match.group(1)) if context_match else ""
        combined = clean_text(" ".join([title, listing_context, detail_text]))
        location_match = re.search(r"([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})", combined)
        city, state = _city_state_from_location(location_match.group(1) if location_match else "", agency)

        posted = ""
        posted_match = re.search(r"\bPosted:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", listing_context)
        if posted_match:
            posted = posted_match.group(1)
        closing = ""
        closing_match = re.search(r"\bClosing Date:\s*([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", listing_context)
        if closing_match:
            closing = closing_match.group(1)

        employment_type = ""
        if re.search(r"\bPart Time\b|\bPart-Time\b", listing_context, flags=re.IGNORECASE):
            employment_type = "Part-time"
        elif re.search(r"\bFull Time\b|\bFull-Time\b", listing_context, flags=re.IGNORECASE):
            employment_type = "Full-time"

        normalized_jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined),
                posted_date=posted,
                closing_date=closing,
                description=detail_text,
                raw_context=combined,
                extra_fields={"employment_type": employment_type},
            )
        )

    return normalized_jobs


def _applicantpro_detail_text(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "lxml")
    parts = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        postings = data if isinstance(data, list) else [data]
        for posting in postings:
            if not isinstance(posting, dict) or posting.get("@type") != "JobPosting":
                continue
            parts.extend(
                clean_text(value)
                for value in [
                    posting.get("title"),
                    _strip_html(posting.get("description")),
                    posting.get("datePosted"),
                    posting.get("validThrough"),
                    posting.get("employmentType"),
                ]
                if value
            )

    for selector in [
        'meta[property="og:description"]',
        'meta[name="description"]',
    ]:
        node = soup.select_one(selector)
        if node and node.get("content"):
            parts.append(clean_text(node["content"]))

    return clean_text(" ".join(parts)) or clean_text(soup.get_text(" ", strip=True))


def scrape_miami_dade_dtpw(agency: dict) -> list[dict]:
    body_text = ""
    current_url = agency["jobs_url"]
    detail_text_by_job_id = {}
    cached_by_job_id = {}
    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            page.goto(agency["jobs_url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            page.get_by_role("link", name="View All Jobs").click(timeout=7000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            page.get_by_text("Transportation & Public Works").first.click(timeout=7000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=5000)
            current_url = page.url

            listing = body_text.split("jobs found.", 1)[-1]
            preview_pattern = re.compile(
                r"(?P<title>[^\n]+)\n"
                r"Job ID(?P<job_id>\d+)\n"
                r"Location(?P<location>[^\n]*)\n"
                r"Department(?P<department>[^\n]*)\n"
                r"Job Family(?P<job_family>[^\n]*)\n"
                r"Business Unit(?P<business_unit>[^\n]*)\n"
                r"Posted Date(?P<posted_date>\d{2}/\d{2}/\d{4})\n"
                r"Close Date(?P<close_date>\d{2}/\d{2}/\d{4})",
            )
            detail_targets = [
                (clean_text(match.group("title")), clean_text(match.group("job_id")))
                for match in preview_pattern.finditer(listing)
                if clean_text(match.group("business_unit")) == "Transportation & Public Works"
            ]
            live_detail_targets = []
            for title, job_id in detail_targets:
                cached = cached_job(agency["agency"], requisition_id=job_id, title=title)
                cached_by_job_id[job_id] = cached
                if has_cached_detail(cached):
                    detail_text_by_job_id[job_id] = cached_detail_text(cached)
                else:
                    live_detail_targets.append((title, job_id))

            if live_detail_targets:
                try:
                    page.get_by_text(live_detail_targets[0][0]).first.click(timeout=7000)
                    page.wait_for_timeout(3000)
                    remaining_ids = {job_id for _, job_id in live_detail_targets}
                    for _ in detail_targets:
                        detail_text = clean_text(page.locator("body").inner_text(timeout=5000))
                        job_id_match = re.search(r"\bJob ID\s*(\d+)", detail_text, flags=re.IGNORECASE)
                        if job_id_match and job_id_match.group(1) in remaining_ids:
                            job_id = job_id_match.group(1)
                            detail_text_by_job_id[job_id] = detail_text
                            remaining_ids.discard(job_id)
                            if not remaining_ids:
                                break
                        try:
                            page.get_by_text("Next Job", exact=True).click(timeout=5000)
                            page.wait_for_timeout(2500)
                        except PlaywrightError:
                            break
                except PlaywrightError:
                    pass
            browser.close()
    except PlaywrightError:
        return []

    jobs = []
    listing = body_text.split("jobs found.", 1)[-1]
    pattern = re.compile(
        r"(?P<title>[^\n]+)\n"
        r"Job ID(?P<job_id>\d+)\n"
        r"Location(?P<location>[^\n]*)\n"
        r"Department(?P<department>[^\n]*)\n"
        r"Job Family(?P<job_family>[^\n]*)\n"
        r"Business Unit(?P<business_unit>[^\n]*)\n"
        r"Posted Date(?P<posted_date>\d{2}/\d{2}/\d{4})\n"
        r"Close Date(?P<close_date>\d{2}/\d{2}/\d{4})",
    )
    for match in pattern.finditer(listing):
        fields = {key: clean_text(value) for key, value in match.groupdict().items()}
        if fields.get("business_unit") != "Transportation & Public Works":
            continue
        detail_text = detail_text_by_job_id.get(fields["job_id"], "")
        cached = cached_by_job_id.get(fields["job_id"]) or cached_job(
            agency["agency"],
            requisition_id=fields["job_id"],
            title=fields["title"],
        )
        salary_text = _miami_salary(detail_text) or cached.get("salary_text", "")
        raw_context = clean_text(
            " ".join(
                [
                    *(f"{key} {value}" for key, value in fields.items()),
                    detail_text,
                    cached.get("salary_text", ""),
                ]
            )
        )
        jobs.append(
            normalize_job(
                title=fields["title"],
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=current_url,
                platform=agency["platform"],
                salary_text=salary_text or extract_salary(raw_context),
                posted_date=fields.get("posted_date", ""),
                closing_date=fields.get("close_date", ""),
                category=fields.get("job_family") or None,
                description=detail_text or cached.get("description", ""),
                raw_context=raw_context,
                extra_fields={
                    "requisition_id": fields["job_id"],
                    "department": fields.get("department", ""),
                    "work_location": fields.get("location", ""),
                },
            )
        )
    return jobs


def _miami_salary(text: str) -> str:
    text = clean_text(text)
    min_match = re.search(r"\bMinimum\s+Rate\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    max_match = re.search(r"\bMaximum\s+Rate\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    min_freq = re.search(r"\bMin\s+Pay\s+Frequency\s*([A-Za-z]+)", text, flags=re.IGNORECASE)
    max_freq = re.search(r"\bMax\s+Pay\s+Frequency\s*([A-Za-z]+)", text, flags=re.IGNORECASE)
    if not min_match and not max_match:
        return ""

    def fmt(value: str) -> str:
        return f"${float(value):,.2f}"

    unit = clean_text((max_freq or min_freq).group(1) if (max_freq or min_freq) else "")
    if min_match and max_match:
        return clean_text(f"{fmt(min_match.group(1))} - {fmt(max_match.group(1))} {unit}")
    match = min_match or max_match
    return clean_text(f"{fmt(match.group(1))} {unit}")


def scrape_uta_custom(agency: dict) -> list[dict]:
    markdown = _jina_markdown(agency["jobs_url"])
    entries = []
    seen_urls = set()
    blocks = re.split(r"\nJob ID:\s*", markdown)
    for block in blocks[1:]:
        job_id = clean_text(block.splitlines()[0])
        title_match = re.search(r"#+\s+\[([^\]]+)\]\((https://careers\.rideuta\.com/jobs/[^)]+)\)", block)
        if not title_match:
            continue
        title, source_url = title_match.groups()
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        location_match = re.search(r"Location:\s+([^\n]+)", block)
        posted_match = re.search(r"Date posted\s+([0-9.]+)", block)
        location = clean_text(location_match.group(1) if location_match else "")
        city, state = _city_state_from_location(location, agency)
        cached = cached_job(agency["agency"], source_url=source_url, requisition_id=job_id, title=title)
        entries.append(
            {
                "title": clean_text(title),
                "source_url": source_url,
                "job_id": job_id,
                "location": location,
                "city": city,
                "state": state,
                "block": block,
                "posted_date": clean_text(posted_match.group(1) if posted_match else ""),
                "cached": cached,
            }
        )

    detail_markdowns = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(JINA_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_jina_markdown, entry["source_url"]): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                detail_markdowns[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        cached = entry["cached"]
        description = _markdown_to_text(detail_markdowns.get(entry["source_url"], "")) or cached_detail_text(cached)
        raw_context = clean_text(
            " ".join(
                [
                    entry["title"],
                    entry["job_id"],
                    entry["location"],
                    entry["block"],
                    description,
                    cached.get("salary_text", ""),
                ]
            )
        )
        jobs.append(
            normalize_job(
                title=entry["title"],
                agency=agency["agency"],
                city=entry["city"],
                state=entry["state"],
                source_url=entry["source_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context) or cached.get("salary_text", ""),
                posted_date=entry["posted_date"] or cached.get("posted_date", ""),
                description=description,
                raw_context=raw_context,
                extra_fields={"requisition_id": entry["job_id"]},
            )
        )
    return jobs


def scrape_via_custom(agency: dict) -> list[dict]:
    body_text = ""
    links = []

    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            page.goto(agency["jobs_url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text(timeout=5000)
            for index in range(min(page.locator("a").count(), 500)):
                link = page.locator("a").nth(index)
                text = clean_text(link.inner_text(timeout=500))
                href = link.get_attribute("href") or ""
                if text and "JobPosting" in href:
                    links.append((text, urljoin(agency["jobs_url"], href)))
            browser.close()
    except PlaywrightError:
        return []

    detail_urls = [source_url for _, source_url in links]
    detail_texts = _via_detail_texts(detail_urls)
    missing_detail_urls = [source_url for source_url in detail_urls if not detail_texts.get(source_url)]
    if missing_detail_urls:
        detail_texts.update(_render_many_pages(missing_detail_urls, wait_ms=3000))
    detail_urls_by_title = {}
    for title, source_url in links:
        detail_urls_by_title.setdefault(title, source_url)

    def format_usd_salary(value: str) -> str:
        value = clean_text(value)
        range_match = re.match(
            r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:[-–]|to)\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(\s+USD\s+per\s+(?:year|hour))",
            value,
            flags=re.IGNORECASE,
        )
        if range_match:
            low, high, unit = range_match.groups()
            return f"${low} - ${high}{unit}"

        single_match = re.match(
            r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(\s+USD\s+per\s+(?:year|hour))",
            value,
            flags=re.IGNORECASE,
        )
        if single_match:
            amount, unit = single_match.groups()
            return f"${amount}{unit}"
        return value

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    jobs = []
    try:
        index = lines.index("Title") + 7
    except ValueError:
        return jobs

    while index < len(lines):
        if lines[index] in {"First Page", "Previous Page", "Next Page", "Last Page"}:
            break
        if lines[index] == "Featured":
            index += 1
        if index + 5 >= len(lines):
            break

        title, job_id, location, category, work_type, posted_date = lines[index : index + 6]
        index += 6
        closing_date = ""
        if index < len(lines) and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", lines[index]):
            closing_date = lines[index]
            index += 1

        if not re.fullmatch(r"\d+", job_id):
            index += 1
            continue
        source_url = detail_urls_by_title.get(title, agency["jobs_url"])
        detail_text = clean_text(detail_texts.get(source_url, ""))
        salary_match = re.search(
            r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:[-–]|to)\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?\s+USD\s+per\s+(?:year|hour)\b"
            r"|\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s+USD\s+per\s+(?:year|hour)\b",
            detail_text,
            flags=re.IGNORECASE,
        )
        salary_text = format_usd_salary(salary_match.group(0)) if salary_match else ""
        city, state = _city_state_from_location(location.replace("US:TX:", ""), agency)
        raw_context = clean_text(
            " ".join([title, job_id, location, category, work_type, posted_date, closing_date, salary_text, detail_text])
        )
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=salary_text or extract_salary(raw_context),
                posted_date=posted_date,
                closing_date=closing_date,
                category=category,
                description=detail_text,
                raw_context=raw_context,
                extra_fields={"requisition_id": job_id, "employment_type": work_type},
            )
        )
    return jobs


def _via_detail_texts(urls: list[str]) -> dict[str, str]:
    unique_urls = list(dict.fromkeys(url for url in urls if url))
    if not unique_urls:
        return {}

    details = {}
    workers = min(8, len(unique_urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_via_detail_text, url): url for url in unique_urls}
        for future in as_completed(futures):
            details[futures[future]] = future.result()
    return details


def _via_detail_text(url: str) -> str:
    parsed = urlparse(url)
    resource_match = re.search(r"/navigation/(.+?)\.JobPostingDisplayNav", parsed.path)
    if not resource_match:
        return ""

    resource = unquote(resource_match.group(1))
    form_path = parsed.path.replace("/navigation/", "/form/").replace(".JobPostingDisplayNav", ".JobPostingDisplay")
    form_url = f"{parsed.scheme}://{parsed.netloc}{form_path}"
    params = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
    params.update(
        {
            "pageop": "load",
            "pagesize": "1",
            "navigation": f"{resource}.JobPostingDisplayNav",
        }
    )

    try:
        session = requests.Session()
        session.get(url, headers=HEADERS, timeout=30)
        response = session.get(
            form_url,
            params=params,
            headers={**HEADERS, "Accept": "application/json, text/plain, */*", "Referer": url},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return ""

    fields = data.get("fields") or {}

    def field_text(name: str) -> str:
        field = fields.get(name) or {}
        value = field.get("value") if isinstance(field, dict) else field
        return _strip_html(str(value or ""))

    return clean_text(
        " ".join(
            value
            for value in [
                field_text("_op_Description_spc_translation_cp_"),
                field_text("_op_JobRequisitionLocationCategoryWorkType_spc_translation_cp_"),
                field_text("_op_FormattedSalaryRangeAmountWithCurrencyCodeAndPayRate_spc_translation_cp_"),
                field_text("_op_PositionDescription_spc_translation_cp_"),
            ]
            if value
        )
    )


def scrape_foothill_custom(agency: dict) -> list[dict]:
    body_text, _ = _render_page(agency["jobs_url"], wait_ms=7000)
    section_match = re.search(r"Open Positions\s+(.+?)\s+Application\s+", body_text, flags=re.DOTALL | re.IGNORECASE)
    if not section_match:
        return []

    lines = [line.strip() for line in section_match.group(1).splitlines() if line.strip()]
    jobs = []
    index = 0
    while index < len(lines):
        title = clean_text(lines[index])
        description_lines = []
        index += 1
        while index < len(lines) and not (
            index + 1 < len(lines)
            and lines[index + 1].lower().startswith(("this position", "under the direction", "the incumbent"))
            and len(lines[index]) <= 100
        ):
            description_lines.append(lines[index])
            index += 1
        description = clean_text(" ".join(description_lines))
        if title and description:
            raw_context = clean_text(" ".join([title, description]))
            jobs.append(
                normalize_job(
                    title=title,
                    agency=agency["agency"],
                    city=agency["city"],
                    state=agency["state"],
                    source_url=agency["jobs_url"],
                    platform=agency["platform"],
                    salary_text=extract_salary(raw_context),
                    description=description,
                    raw_context=raw_context,
                )
            )
    return jobs


def scrape_gcrta_custom(agency: dict) -> list[dict]:
    body_text = ""
    current_url = agency["jobs_url"]
    try:
        with _sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--headless=new"])
            page = browser.new_page(viewport={"width": 1366, "height": 1200})
            page.goto(agency["jobs_url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            page.locator("#Go").click(timeout=7000)
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=5000)
            current_url = page.url
            browser.close()
    except PlaywrightError:
        return []

    if "No results found" in body_text or "No search conducted" in body_text:
        return []

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    jobs = []
    try:
        index = lines.index("Name") + 7
    except ValueError:
        return jobs

    while index + 5 < len(lines):
        if lines[index].startswith("Copyright"):
            break
        name, title, category, location, posted_date, employment_type = lines[index : index + 6]
        index += 6
        if title in {"Job Title", "No results found."}:
            continue
        city, state = _city_state_from_location(location, agency)
        raw_context = clean_text(" ".join([name, title, category, location, posted_date, employment_type]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=current_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                posted_date=posted_date,
                category=category,
                raw_context=raw_context,
                extra_fields={"employment_type": employment_type},
            )
        )
    return jobs


def _parse_panynj_listing_markdown(markdown: str, agency: dict) -> list[dict]:
    entries = []
    seen_urls = set()
    title_matches = list(
        re.finditer(
            r"(?im)^\s*Job Title:\s*\[([^\]]+)\]\((https://www\.jointheportauthority\.com/jobs/[^)]+)\)\s*$",
            markdown,
        )
    )

    for index, match in enumerate(title_matches):
        block_end = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(markdown)
        block = markdown[match.end() : block_end]
        title = clean_text(match.group(1))
        source_url = urljoin(agency["jobs_url"], match.group(2))
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)

        job_id = _markdown_label_value(block, "Job ID")
        if not job_id:
            continue

        family = _markdown_label_value(block, "Job Family")
        department = _markdown_label_value(block, "Department")
        location = _markdown_label_value(block, "Location")
        city, state = _city_state_from_location(location, agency)
        cached = cached_job(agency["agency"], source_url=source_url, requisition_id=job_id, title=title)
        entries.append(
            {
                "title": title,
                "source_url": source_url,
                "job_id": job_id,
                "family": family,
                "department": department,
                "location": location,
                "city": city,
                "state": state,
                "cached": cached,
            }
        )

    return entries


def scrape_panynj_custom(agency: dict) -> list[dict]:
    markdown = _jina_markdown(agency["jobs_url"])
    entries = _parse_panynj_listing_markdown(markdown, agency)

    detail_markdowns = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(JINA_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_jina_markdown, entry["source_url"]): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                detail_markdowns[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        cached = entry["cached"]
        description = _markdown_to_text(detail_markdowns.get(entry["source_url"], "")) or cached_detail_text(cached)
        raw_context = clean_text(
            " ".join(
                [
                    entry["title"],
                    entry["job_id"],
                    entry["family"],
                    entry["department"],
                    entry["location"],
                    description,
                    cached.get("salary_text", ""),
                ]
            )
        )
        jobs.append(
            normalize_job(
                title=entry["title"],
                agency=agency["agency"],
                city=entry["city"],
                state=entry["state"],
                source_url=entry["source_url"],
                platform=agency["platform"],
                salary_text=extract_salary(raw_context) or cached.get("salary_text", ""),
                category=entry["family"] or cached.get("category") or None,
                description=description,
                raw_context=raw_context,
                extra_fields={"requisition_id": entry["job_id"], "department": entry["department"]},
            )
        )
    return jobs


def _scrape_transdev_jobs(agency: dict) -> list[dict]:
    markdown = _jina_markdown(agency["jobs_url"])
    entries = []
    seen_urls = set()
    pattern = re.compile(r"##\s+\[([^\]]+?)\]\((https://transdevna\.jobs/[^)]+/job/)\)", flags=re.IGNORECASE)

    for title, source_url in pattern.findall(markdown):
        if source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        title = re.sub(r"\s+[A-Z][A-Za-z .'-]+,\s+[A-Z]{2}$", "", clean_text(title)).strip()
        cached = cached_job(agency["agency"], source_url=source_url, title=title)
        entries.append({"title": title, "source_url": source_url, "cached": cached})

    detail_markdowns = {}
    pending = [entry for entry in entries if not has_cached_detail(entry["cached"])]
    if pending:
        workers = min(JINA_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_jina_markdown, entry["source_url"]): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                detail_markdowns[entry["source_url"]] = future.result()

    jobs = []
    for entry in entries:
        cached = entry["cached"]
        title = entry["title"]
        source_url = entry["source_url"]
        detail_text = _markdown_to_text(detail_markdowns.get(source_url, "")) or cached_detail_text(cached)
        raw_context = clean_text(" ".join([title, detail_text]))
        city, state = agency["city"], agency["state"]
        location_match = re.search(r"\b([A-Z][A-Za-z .'-]+,\s+[A-Z]{2})\b", raw_context)
        if location_match:
            city, state = _city_state_from_location(location_match.group(1), agency)
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=city,
                state=state,
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context) or cached.get("salary_text", ""),
                description=detail_text,
                raw_context=raw_context,
            )
        )

    return jobs


def scrape_static_job_links(agency: dict) -> list[dict]:
    if "transdevna.jobs" in agency["jobs_url"]:
        return _scrape_transdev_jobs(agency)

    body_text, links = _render_page(agency["jobs_url"], wait_ms=7000)
    candidates = []
    seen_urls = set()
    extra_patterns = [re.compile(pattern, re.I) for pattern in agency.get("job_link_patterns", [])]

    for title, source_url in links:
        title = clean_text(title)
        if not title or source_url in seen_urls:
            continue
        blob = f"{title} {source_url}".lower()
        if not (
            re.search(r"(/jobs/\d+|gnk=job|jobid=|positiondetails|candidateexperience/.+/job/|/job/)", source_url, re.I)
            or any(pattern.search(blob) for pattern in extra_patterns)
        ):
            continue
        if title.lower() in {
            "jobs",
            "careers",
            "apply",
            "apply here",
            "click here",
            "view job",
            "read more",
            "skip to main content",
            "find jobs",
            "search jobs",
            "job type",
            "all positions",
            "career fairs",
            "hiring programs",
            "join our team",
            "current employees",
        }:
            continue
        if len(title) < 4 or len(title) > 120:
            continue
        if re.search(r"\b(home|privacy|legal|facebook|twitter|linkedin|instagram|translate|contact)\b", title, re.I):
            continue
        seen_urls.add(source_url)
        cached = cached_job(agency["agency"], source_url=source_url, title=title)
        candidates.append({"title": title, "source_url": source_url, "cached": cached})

    detail_texts = {}
    pending = [
        candidate
        for candidate in candidates
        if candidate["source_url"].startswith("http") and not has_cached_detail(candidate["cached"])
    ]
    if pending:
        workers = min(STATIC_DETAIL_WORKERS, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_detail_text, candidate["source_url"]): candidate for candidate in pending}
            for future in as_completed(futures):
                candidate = futures[future]
                detail_texts[candidate["source_url"]] = future.result()

    render_urls = [
        candidate["source_url"]
        for candidate in candidates
        if candidate["source_url"].startswith("http")
        and not has_cached_detail(candidate["cached"])
        and (
            not detail_texts.get(candidate["source_url"])
            or ("transdevna.jobs" in candidate["source_url"] and not extract_salary(detail_texts[candidate["source_url"]]))
        )
    ]
    rendered_details = _render_many_pages(render_urls, wait_ms=8000) if render_urls else {}

    jobs = []
    for candidate in candidates:
        title = candidate["title"]
        source_url = candidate["source_url"]
        cached = candidate["cached"]
        detail_text = detail_texts.get(source_url) or cached_detail_text(cached)
        if source_url in rendered_details and rendered_details[source_url]:
            detail_text = rendered_details[source_url]
        combined = clean_text(" ".join([title, body_text[:1500], detail_text]))

        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(combined) or cached.get("salary_text", ""),
                description=detail_text or cached.get("description", ""),
                raw_context=combined,
            )
        )

    return jobs


def _slice_static_section(text: str, agency: dict) -> str:
    text = "\n".join(clean_text(line) for line in str(text or "").splitlines() if clean_text(line))
    start = agency.get("section_start")
    end = agency.get("section_end")
    if start and start.lower() in text.lower():
        index = text.lower().find(start.lower())
        text = text[index:]
    if end and end.lower() in text.lower():
        index = text.lower().find(end.lower())
        text = text[:index]
    return text


def _static_text_title(line: str) -> bool:
    line = clean_text(line)
    if len(line) < 4 or len(line) > 100:
        return False
    if re.match(r"^[^\w$]", line):
        return False
    if re.fullmatch(r"[A-Za-z]+\s+\d{1,2},\s+\d{4}|open until filled", line, re.I):
        return False
    if re.search(r"\.(pdf|docx?)$", line, re.I):
        return False
    if "$" in line and not re.search(r"[A-Za-z]", line):
        return False
    if re.search(
        r"\b(menu|route|schedule|fare|alert|privacy|copyright|facebook|instagram|linkedin|"
        r"administrative positions|open positions|compensation package|position overview|"
        r"abilities|demonstrated driving record|selection process|application review|oral interview|"
        r"pre-employment process|disclaimer|employment application|salaries & benefits|"
        r"link to|flyer|application form|apply@|please fill|please download|read more|"
        r"job details|job title|job id|description|salary|qualifications|special requirements|"
        r"miscellaneous|preview|continue|cancel|download application|fillable application|"
        r"feature this listing|pay later|proceed to checkout|go back|free|total|tools)\b",
        line,
        re.I,
    ):
        return False
    if line.endswith((".", ":", "?", "!")):
        return False
    words = line.split()
    if len(words) > 10:
        return False
    return bool(re.search(r"[A-Za-z]", line))


def _static_page_text_and_links(url: str) -> tuple[str, list[tuple[str, str]]]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        text = soup.get_text("\n", strip=True)
        links = [
            (clean_text(link.get_text(" ", strip=True)), urljoin(url, link["href"]))
            for link in soup.find_all("a", href=True)
        ]
        return text, links
    except requests.RequestException:
        return "", []


def scrape_static_text_jobs(agency: dict) -> list[dict]:
    body_text, links = _static_page_text_and_links(agency["jobs_url"])
    if not body_text:
        markdown = _jina_markdown(agency["jobs_url"])
        body_text = _markdown_to_text(markdown)
    if not body_text:
        body_text, links = _render_page(agency["jobs_url"], wait_ms=7000)

    section = _slice_static_section(body_text, agency)
    if re.search(r"\b(no current vacancies|no current job openings|not currently accepting applications)\b", section, re.I) and "$" not in section:
        return []

    jobs = {}
    seen_titles = set()
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    default_allow_terms = [
        "operator",
        "driver",
        "mechanic",
        "technician",
        "manager",
        "supervisor",
        "director",
        "analyst",
        "planner",
        "engineer",
        "coordinator",
        "administrator",
        "assistant",
        "worker",
        "specialist",
        "clerk",
        "accountant",
        "inspector",
        "dispatcher",
        "attendant",
        "intern",
        "trainee",
        "officer",
        "representative",
        "maintenance",
        "utility",
    ]
    allow_terms = [term.lower() for term in agency.get("title_allow_terms", default_allow_terms)]
    detail_text_cache = {agency["jobs_url"]: body_text}

    apply_links = [
        url
        for text, url in links
        if re.search(r"\b(apply|application|open positions|view open|more information)\b", f"{text} {url}", re.I)
        and not re.search(r"\.(?:pdf|docx?|xlsx?)(?:$|\?)", url, re.I)
    ]

    for index, line in enumerate(lines):
        original_line = clean_text(re.sub(r"^(?:#+\s*)", "", line))
        title = original_line
        title = re.sub(r"\s+[-–]\s+\$.*$", "", title).strip()
        if title.lower() in seen_titles or not _static_text_title(title):
            continue
        if allow_terms and not any(term in title.lower() for term in allow_terms):
            continue

        window = clean_text(" ".join(lines[index : index + 18]))
        if not re.search(
            r"\b(salary|hourly|annual|compensation|full[- ]time|part[- ]time|apply|application|"
            r"deadline|open until filled|recruiting|more information)\b|\$",
            window,
            re.I,
        ):
            continue

        seen_titles.add(title.lower())
        source_url = apply_links[0] if apply_links else agency["jobs_url"]
        cached = cached_job(agency["agency"], source_url=source_url, title=title)
        if has_cached_detail(cached):
            detail_text = cached_detail_text(cached)
        elif source_url.startswith("http"):
            if source_url not in detail_text_cache:
                detail_text_cache[source_url] = _detail_text(source_url)
            detail_text = detail_text_cache[source_url]
        else:
            detail_text = ""
        raw_context = clean_text(" ".join([title, window, detail_text, cached.get("salary_text", "")]))
        job = normalize_job(
            title=title,
            agency=agency["agency"],
            city=agency["city"],
            state=agency["state"],
            source_url=source_url,
            platform=agency["platform"],
            salary_text=extract_salary(original_line) or extract_salary(raw_context) or cached.get("salary_text", ""),
            description=detail_text or cached.get("description", "") or window,
            raw_context=raw_context,
        )
        jobs[job["job_id"]] = job

    return list(jobs.values())


def scrape_calopps(agency: dict) -> list[dict]:
    response = requests.get(agency["jobs_url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    text = clean_text(soup.get_text(" ", strip=True))
    if "There are no job openings" in text:
        return []

    jobs = []
    seen_urls = set()
    for link in soup.find_all("a", href=True):
        source_url = urljoin(agency["jobs_url"], link["href"])
        if "/job/" not in source_url and "/jobs/" not in source_url:
            continue
        title = clean_text(link.get_text(" ", strip=True))
        if not title or source_url in seen_urls:
            continue
        seen_urls.add(source_url)
        detail_text = _detail_text(source_url)
        raw_context = clean_text(" ".join([title, detail_text]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                description=detail_text,
                raw_context=raw_context,
            )
        )
    return jobs


def scrape_prt_custom(agency: dict) -> list[dict]:
    body_text, _ = _render_page(agency["jobs_url"], wait_ms=8000)
    listing = body_text.split("Working at Pittsburgh Regional Transit", 1)[0]
    chunks = re.split(r"\nApply\s+More Details\n|\nApply\s+More Details\s+|\nApply\s+.*?More Details\n", listing)
    jobs = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines or lines[0] in {"CURRENT JOB OPENINGS"} or re.fullmatch(r"\d+", lines[0]):
            continue
        if "CURRENT JOB OPENINGS" in lines[0] and len(lines) > 1:
            lines = lines[1:]
        title = clean_text(lines[0])
        if not title or len(title) > 140:
            continue
        description = clean_text(" ".join(lines[1:]))
        raw_context = clean_text(" ".join([title, description]))
        salary_text = extract_salary(title) or extract_salary(raw_context)
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=agency["jobs_url"],
                platform=agency["platform"],
                salary_text=salary_text,
                description=description,
                raw_context=raw_context,
            )
        )
    return jobs


def scrape_norta_custom(agency: dict) -> list[dict]:
    body_text, links = _render_page(agency["jobs_url"], wait_ms=7000)
    section = body_text.split("We pride ourselves", 1)[0]
    matches = re.findall(
        r"\n([A-Z][^\n]{8,120})\n\s+Are you the .+? applying for it is a breeze\. (?:Please apply here\.|Best of luck! Apply here\.)",
        section,
        flags=re.DOTALL,
    )
    apply_links = [href for text, href in links if "apply here" in text.lower()]
    jobs = []
    for index, title in enumerate(matches):
        title = clean_text(title)
        source_url = apply_links[index] if index < len(apply_links) else agency["jobs_url"]
        detail_text = _detail_text(source_url) if source_url.startswith("http") else ""
        if source_url.startswith("http") and not extract_salary(detail_text):
            rendered_detail, _ = _render_page(source_url, wait_ms=8000)
            if rendered_detail:
                detail_text = rendered_detail
        raw_context = clean_text(" ".join([title, section, detail_text]))
        jobs.append(
            normalize_job(
                title=title,
                agency=agency["agency"],
                city=agency["city"],
                state=agency["state"],
                source_url=source_url,
                platform=agency["platform"],
                salary_text=extract_salary(raw_context),
                description=detail_text,
                raw_context=raw_context,
            )
        )
    return jobs
