import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from scrapers import mta_browser, mta_custom


AGENCY = {"agency": "MTA", "city": "New York", "state": "NY", "platform": "mta_custom",
          "jobs_url": "https://careers.mta.org/search/jobs"}


def listing(number=1, total=1):
    next_link = f'<a rel="next" href="/search/jobs/in?page={number + 1}#">Next</a>' if number < total else ""
    return f'''<main><div class="jobs-section__item"><h2><a href="/jobs/1800000{number}-analyst">Schedule Analyst {number}</a></h2>
    <div>1700{number}</div><div>New York, NY</div><div>Operations Planning</div>
    <div>Date Posted: Nov 9, 2026</div></div>Showing {number}-{number} of {total} results{next_link}</main>'''


DETAIL = '''<main><article><h1>Schedule Analyst</h1><table>
<tr><td>JOB ID:</td><td>17001</td></tr><tr><td>SALARY RANGE:</td><td>$80,000 to $100,000</td></tr>
</table><p>Plan rail schedules and crew assignments.</p></article></main>'''


def page(html):
    return SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                           content=AsyncMock(return_value=html), wait_for_timeout=AsyncMock(), close=AsyncMock())


class MtaTransportTests(unittest.TestCase):
    def test_auto_transitions_from_failed_http_to_browser(self):
        expected = [{"title": "Browser result"}]
        with patch.dict(os.environ, {"MTA_TRANSPORT": "auto"}):
            with patch.object(mta_custom, "_scrape_careers_summaries", side_effect=mta_custom.MtaListingUnavailable("challenge")):
                with patch.object(mta_browser, "scrape_mta_browser", return_value=expected) as browser:
                    self.assertEqual(mta_custom.scrape_mta(AGENCY), expected)
        browser.assert_called_once_with(AGENCY)

    def test_browser_mode_skips_all_http_requests(self):
        with patch.dict(os.environ, {"MTA_TRANSPORT": "browser"}):
            with patch.object(mta_custom, "_scrape_careers_summaries") as http:
                with patch.object(mta_browser, "scrape_mta_browser", return_value=[]) as browser:
                    self.assertEqual(mta_custom.scrape_mta(AGENCY), [])
        http.assert_not_called()
        browser.assert_called_once_with(AGENCY)

    def test_http_mode_does_not_open_browser(self):
        with patch.dict(os.environ, {"MTA_TRANSPORT": "http"}):
            with patch.object(mta_custom, "_scrape_careers_summaries", side_effect=mta_custom.MtaListingUnavailable("challenge")):
                with patch.object(mta_browser, "scrape_mta_browser") as browser:
                    with self.assertRaises(mta_custom.MtaListingUnavailable):
                        mta_custom.scrape_mta(AGENCY)
        browser.assert_not_called()

    def test_grid_parser_reads_unlabelled_id_location_and_department(self):
        jobs = mta_custom._parse_careers_search_page(listing(), AGENCY, mta_custom.SEARCH_URL)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["requisition_id"], "17001")
        self.assertEqual(jobs[0]["location"], "New York, NY")
        self.assertEqual(jobs[0]["department"], "Operations Planning")
        self.assertEqual(jobs[0]["posted_date_iso"], "2026-11-09")

    def test_parser_reads_card_observed_on_live_mta_board(self):
        html = '''<div class="jobs-section__item padded-v-small"><div class="row">
        <div class="large-3 columns"><h2 class="mta-flex mta-gap-2"><div class="mta-new-job">NEW</div>
        <a href="https://careers.mta.org/jobs/18457903-transit-management-analyst-series">Transit Management Analyst Series</a></h2></div>
        <div class="columns large-2"><span class="hide">Job ID: </span><span class="heading-5 color-text-grey">17983&nbsp;</span></div>
        <div class="large-2 columns"><span class="hide">Location: </span><span class="heading-5 color-text-grey"> Brooklyn, NY &nbsp; </span></div>
        <div class="medium-3 columns"><span class="hide">Department: </span><span class="heading-5 color-text-grey">Maintenance Planning</span>&nbsp;</div>
        <div class="large-2 columns"><span class="hide-for-large">Date Posted: </span><span class="heading-5 color-text-grey">Nov 6, 2026</span></div>
        </div></div>'''
        jobs = mta_custom._parse_careers_search_page(html, AGENCY, mta_custom.SEARCH_URL)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["requisition_id"], "17983")
        self.assertEqual(jobs[0]["location"], "Brooklyn, NY")
        self.assertEqual(jobs[0]["department"], "Maintenance Planning")
        self.assertEqual(jobs[0]["posted_date_iso"], "2026-11-06")


class MtaBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_challenge_to_finish_without_reloading(self):
        browser_page = page("")
        browser_page.goto.return_value.status = 403
        browser_page.content.side_effect = ["<title>Just a moment...</title>", listing()]
        _, summaries = await mta_browser._read_page(browser_page, mta_custom.SEARCH_URL, listing=True, agency=AGENCY)
        self.assertEqual(len(summaries), 1)
        browser_page.goto.assert_awaited_once()
        browser_page.wait_for_timeout.assert_awaited_once()

    async def test_persistent_challenge_has_bounded_wait_and_no_fake_success(self):
        browser_page = page("<title>Just a moment...</title>")
        with patch.object(mta_browser.time, "monotonic", side_effect=[0, 61]):
            with self.assertRaisesRegex(mta_custom.MtaListingUnavailable, "still requires browser verification"):
                await mta_browser._read_page(browser_page, mta_custom.SEARCH_URL, listing=True, agency=AGENCY)

    async def test_complete_browser_pagination_ignores_configured_http_page_size(self):
        first = listing(1, 2)
        second = listing(2, 2)
        results = [(first, mta_custom._parse_careers_search_page(first, AGENCY, mta_custom.SEARCH_URL)),
                   (second, mta_custom._parse_careers_search_page(second, AGENCY, mta_custom.SEARCH_URL))]
        with patch.object(mta_browser, "_read_page", new=AsyncMock(side_effect=results)) as read:
            with patch.object(mta_custom, "LISTING_DELAY", 0):
                jobs = await mta_browser._listings(Mock(), AGENCY)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(read.call_args_list[1].args[1], "https://careers.mta.org/search/jobs/in?page=2")

    async def test_browser_does_not_invent_a_next_page_when_link_is_missing(self):
        html = listing(1, 2).split('<a rel="next"')[0]
        summaries = mta_custom._parse_careers_search_page(html, AGENCY, mta_custom.SEARCH_URL)
        with patch.object(mta_browser, "_read_page", new=AsyncMock(return_value=(html, summaries))):
            with self.assertRaisesRegex(mta_custom.MtaListingUnavailable, "missing a next-page link"):
                await mta_browser._listings(Mock(), AGENCY)

    async def test_browser_cannot_report_success_with_missing_job_cards(self):
        html = listing(2, 2)
        summaries = mta_custom._parse_careers_search_page(html, AGENCY, mta_custom.SEARCH_URL)
        with patch.object(mta_browser, "_read_page", new=AsyncMock(return_value=(html, summaries))):
            with self.assertRaisesRegex(mta_custom.MtaListingUnavailable, "1/2 advertised jobs"):
                await mta_browser._listings(Mock(), AGENCY)

    async def test_detail_uses_browser_dom_and_preserves_salary(self):
        details = await mta_browser._read_page(page(DETAIL), "https://careers.mta.org/jobs/18000001-analyst", listing=False, agency=AGENCY)
        self.assertEqual(details["salary_text"], "$80,000 to $100,000")
        self.assertIn("Plan rail schedules", details["full_job_description"])

    async def test_detail_challenge_is_never_a_description(self):
        browser_page = page('<title>Just a moment...</title><article>Checking browser</article>')
        with patch.object(mta_browser.time, "monotonic", side_effect=[0, 61]):
            with self.assertRaises(mta_custom.MtaListingUnavailable):
                await mta_browser._read_page(browser_page, "https://careers.mta.org/jobs/18000001-analyst", listing=False, agency=AGENCY)

    async def test_details_stay_in_shared_context_and_close_tabs(self):
        summary = mta_custom._parse_careers_search_page(listing(), AGENCY, mta_custom.SEARCH_URL)[0]
        summary["cached"] = {}
        detail_page = page(DETAIL)
        context = SimpleNamespace(new_page=AsyncMock(return_value=detail_page))
        with patch.object(mta_browser, "has_cached_detail", return_value=False):
            with patch.object(mta_custom, "_fetch_detail") as curl_detail:
                details = await mta_browser._details(context, [summary], AGENCY)
        self.assertIn(summary["source_url"], details)
        detail_page.close.assert_awaited_once()
        curl_detail.assert_not_called()

    async def test_browser_orchestration_uses_dedicated_profile_and_closes_context(self):
        summary = mta_custom._parse_careers_search_page(listing(), AGENCY, mta_custom.SEARCH_URL)[0]
        context = SimpleNamespace(pages=[Mock()], close=AsyncMock())
        launcher = AsyncMock(return_value=context)
        runtime = MagicMock()
        runtime.__aenter__.return_value = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launcher))
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MTA_BROWSER_PROFILE": directory, "MTA_BROWSER_HEADLESS": "1", "MTA_BROWSER_CHANNEL": "chrome"}):
                with patch("playwright.async_api.async_playwright", return_value=runtime):
                    with patch.object(mta_browser, "_listings", new=AsyncMock(return_value=[summary])):
                        with patch.object(mta_browser, "_details", new=AsyncMock(return_value={summary["source_url"]: mta_custom._parse_detail_page(DETAIL)})):
                            with patch.object(mta_browser, "cached_job", return_value={}):
                                jobs = await mta_browser._scrape(AGENCY)
            self.assertEqual(launcher.call_args.kwargs["user_data_dir"], str(Path(directory).resolve()))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["salary_range_display"], "$80,000 - $100,000")
        self.assertEqual(launcher.call_args.kwargs["args"], ["--headless=new"])
        self.assertFalse(launcher.call_args.kwargs["headless"])
        context.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
