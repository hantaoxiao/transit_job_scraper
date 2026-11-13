"""MTA listings and details in one persistent, JavaScript-capable browser."""

import asyncio
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from normalizer import clean_text
from scrapers.detail_cache import cached_job, has_cached_detail
from scrapers import mta_custom as mta


# Outside the checkout so actions/checkout cannot delete the browser session.
# A manual check and Actions running as the same account use the same profile.
DEFAULT_PROFILE = Path.home() / ".cache" / "transit-job-scraper" / "mta-browser"


def _headless() -> bool:
    value = os.getenv("MTA_BROWSER_HEADLESS")
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes"}
    return not (sys.platform in {"darwin", "win32"} or os.getenv("DISPLAY"))


def _channel() -> str:
    configured = os.getenv("MTA_BROWSER_CHANNEL")
    if configured is not None:
        return "" if configured.lower() == "chromium" else configured
    if Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists() or shutil.which("google-chrome"):
        return "chrome"
    return ""


def _challenge(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    return bool(re.search(r"just a moment|attention required", title, re.I) or soup.select_one(
        '#challenge-running, #challenge-stage, form#challenge-form'
    ))


async def _read_page(page, url: str, *, listing: bool, agency: dict):
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=mta.REQUEST_TIMEOUT * 1000)
    except PlaywrightTimeoutError:
        # Challenge navigation may outlast DOMContentLoaded. Inspect the current
        # page within a bounded wait instead of reloading the challenge.
        response = None
    deadline = time.monotonic() + mta._env_int("MTA_BROWSER_WAIT_SECONDS", 60)
    announced = False
    last_challenge = False
    while True:
        try:
            html = await page.content()
        except Exception:
            if time.monotonic() >= deadline:
                raise
            await page.wait_for_timeout(500)
            continue
        last_challenge = _challenge(html)
        if last_challenge and not announced:
            print("MTA browser is waiting for site verification. If a verification control appears, complete it in the MTA browser window.", flush=True)
            announced = True
        if not last_challenge:
            if response is not None and response.status >= 400 and not announced:
                raise mta.MtaListingUnavailable(f"MTA browser returned HTTP {response.status} for {url}")
            if listing:
                summaries = mta._parse_careers_search_page(html, agency, url)
                if summaries:
                    return html, summaries
                text = clean_text(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
                if re.search(r"\b0 (?:jobs|results) found\b|no (?:jobs|results) (?:found|match)", text, re.I):
                    return html, []
            else:
                # Never mistake a 200 challenge/error page for a job description.
                soup = BeautifulSoup(html, "lxml")
                if mta._json_ld_jobposting(soup) or soup.select_one('.job-description, .job-description__content, article'):
                    details = mta._parse_detail_page(html)
                    if details.get("full_job_description"):
                        return details
        if time.monotonic() >= deadline:
            if last_challenge:
                raise mta.MtaListingUnavailable(
                    "Cloudflare still requires browser verification. Run with MTA_TRANSPORT=browser "
                    "MTA_BROWSER_HEADLESS=0 on the runner's desktop and complete verification in the opened window. "
                    "Use the same MTA_BROWSER_PROFILE for scheduled runs."
                )
            raise mta.MtaListingUnavailable(f"MTA browser found no recognizable {'job cards' if listing else 'job description'} at {url}")
        await page.wait_for_timeout(500)


async def _listings(page, agency: dict) -> list[dict]:
    by_url = {}
    page_url = f"{mta.SEARCH_URL}?{urlencode({'per_page': mta.PER_PAGE})}"
    for number in range(1, mta.MAX_PAGES + 1):
        html, summaries = await _read_page(page, page_url, listing=True, agency=agency)
        if not summaries:
            if number == 1:
                return []
            raise mta.MtaListingUnavailable("MTA browser pagination ended before the advertised result count")
        new = [summary for summary in summaries if summary["source_url"] not in by_url]
        if not new:
            raise mta.MtaListingUnavailable(f"MTA browser pagination repeated page {number}")
        by_url.update((summary["source_url"], summary) for summary in new)
        print(f"MTA browser listing page={number} jobs_found={len(summaries)} total_collected={len(by_url)}", flush=True)
        soup = BeautifulSoup(html, "lxml")
        text = clean_text(soup.get_text(" ", strip=True))
        showing = re.search(r"Showing\s+[\d,]+\s*[-–]\s*([\d,]+)\s+of\s+([\d,]+)\s+results", text, re.I)
        next_link = soup.select_one('a[rel~="next"], .pagination .next a, a.next_page')
        if showing:
            end, total = (int(value.replace(",", "")) for value in showing.groups())
            if end >= total:
                if len(by_url) < total:
                    raise mta.MtaListingUnavailable(f"MTA browser parsed only {len(by_url)}/{total} advertised jobs")
                return list(by_url.values())
        elif not next_link:
            return list(by_url.values())
        if not next_link or not next_link.get("href"):
            raise mta.MtaListingUnavailable("MTA browser listing is missing a next-page link before the advertised last page")
        next_url = urlparse(urljoin(page_url, next_link["href"]))
        if next_url.scheme != "https" or next_url.netloc != urlparse(mta.BASE_URL).netloc or not next_url.path.startswith("/search/"):
            raise mta.MtaListingUnavailable("MTA browser listing has an unexpected next-page destination")
        query = [(key, value) for key, value in parse_qsl(next_url.query, keep_blank_values=True) if key != "per_page"]
        query.append(("per_page", str(mta.PER_PAGE)))
        page_url = next_url._replace(query=urlencode(query), fragment="").geturl()
        if mta.LISTING_DELAY:
            await asyncio.sleep(mta.LISTING_DELAY)
    raise mta.MtaListingUnavailable(f"MTA browser listing exceeded MTA_CAREERS_MAX_PAGES={mta.MAX_PAGES}")


async def _details(context, summaries: list[dict], agency: dict) -> dict:
    pending = asyncio.Queue()
    for summary in summaries:
        if not has_cached_detail(summary["cached"]):
            pending.put_nowait(summary)
    if pending.empty():
        return {}
    print(f"Fetching {pending.qsize()} MTA details through the same browser session.", flush=True)
    results = {}

    async def worker():
        page = await context.new_page()
        try:
            while not pending.empty():
                summary = pending.get_nowait()
                results[summary["source_url"]] = await _read_page(page, summary["source_url"], listing=False, agency=agency)
                if mta.DETAIL_DELAY:
                    await asyncio.sleep(mta.DETAIL_DELAY)
        finally:
            await page.close()

    workers = min(mta._env_int("MTA_BROWSER_DETAIL_WORKERS", 3), pending.qsize())
    tasks = [asyncio.create_task(worker()) for _ in range(workers)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return results


async def _scrape(agency: dict) -> list[dict]:
    from playwright.async_api import async_playwright

    profile = Path(os.getenv("MTA_BROWSER_PROFILE", str(DEFAULT_PROFILE))).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    headless = _headless()
    # Playwright 1.48 requests Chromium's removed old headless mode. Select the
    # current browser's new headless mode explicitly when a display is absent.
    options = {"user_data_dir": str(profile), "headless": False, "viewport": {"width": 1440, "height": 1000}}
    if headless:
        options["args"] = ["--headless=new"]
    channel = _channel()
    if channel:
        options["channel"] = channel
    print(f"MTA browser starting: channel={channel or 'chromium'}, headless={headless}, profile={profile}", flush=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(**options)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            summaries = await _listings(page, agency)
            for summary in summaries:
                summary["cached"] = cached_job(
                    agency["agency"], source_url=summary["source_url"],
                    requisition_id=summary.get("mta_job_id", ""), title=summary["title"],
                )
            details = await _details(context, summaries, agency)
            return [
                mta._build_mta_job(
                    summary, agency,
                    details.get(summary["source_url"]) or mta._cached_job_details(summary["cached"]),
                )
                for summary in summaries
            ]
        finally:
            await context.close()


def scrape_mta_browser(agency: dict) -> list[dict]:
    return asyncio.run(_scrape(agency))
