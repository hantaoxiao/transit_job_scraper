import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

from scrapers import mta_custom


AGENCY = {
    "agency": "MTA",
    "city": "New York",
    "state": "NY",
    "platform": "mta_custom",
}

CACHED_JOB = {
    "job_id": "cached-mta-job",
    "title": "Cached MTA Job",
    "agency": "MTA",
    "city": "New York",
    "state": "NY",
    "source_url": "https://careers.mta.org/jobs/cached-mta-job",
    "platform": "mta_custom",
}

JINA_PAGE_ONE = """
Showing 1 - 100 of 101 results
[Live MTA Job](https://careers.mta.org/jobs/live-mta-job)
Job ID: 12345
Location: New York, NY, United States
Department: Operations
Date Posted: May 18, 2026
"""

STALE_CACHED_DIRECTOR = {
    "all_meaningful_info": (
        "Director Project Management JOB FAMILY: CON GRADE: 006 "
        "SALARY RANGE : $12 9,446 to $1 61,807 DEADLINE: Open Until Filled"
    ),
    "salary_text": "$12",
}

SPLIT_CACHED_DIRECTOR = {
    "all_meaningful_info": STALE_CACHED_DIRECTOR["all_meaningful_info"],
    "salary_text": "$12 9,446 to $1 61,807",
}


class MtaJinaFallbackTests(unittest.TestCase):
    def test_jina_url_uses_http_target_without_double_scheme(self):
        url = mta_custom._jina_url("https://careers.mta.org/search/jobs/?per_page=100")

        self.assertEqual(url, "https://r.jina.ai/http://careers.mta.org/search/jobs/?per_page=100")

    def test_jina_search_pagination_uses_ci_readable_url_shape(self):
        self.assertEqual(
            mta_custom._jina_search_url(2),
            "https://careers.mta.org/search/jobs/?page=2&per_page=100",
        )

    def test_detects_jina_challenge_body(self):
        self.assertTrue(mta_custom._is_jina_unusable_text("Enable JavaScript and cookies to continue"))

    def test_uses_cache_when_first_jina_listing_page_is_blocked(self):
        with patch.object(mta_custom, "_jina_text", side_effect=requests.HTTPError("blocked")):
            with patch.object(mta_custom, "_load_existing_mta_cache", return_value={CACHED_JOB["source_url"]: CACHED_JOB}):
                jobs = mta_custom._scrape_mta_jina(AGENCY)

        self.assertEqual(jobs, [CACHED_JOB])

    def test_merges_first_jina_listing_page_with_cache_without_fetching_later_pages(self):
        with patch.object(mta_custom, "_jina_text", return_value=JINA_PAGE_ONE) as jina_text:
            with patch.object(mta_custom, "_fetch_jina_detail", return_value={}):
                with patch.object(
                    mta_custom,
                    "_load_existing_mta_cache",
                    return_value={CACHED_JOB["source_url"]: CACHED_JOB},
                ):
                    jobs = mta_custom._scrape_mta_jina(AGENCY)

        self.assertEqual(jina_text.call_count, 1)
        self.assertEqual([job["title"] for job in jobs], ["Live MTA Job", "Cached MTA Job"])

    def test_raises_when_later_jina_listing_page_is_blocked_without_cache(self):
        with patch.object(mta_custom, "_jina_text", side_effect=[JINA_PAGE_ONE, requests.HTTPError("blocked")]):
            with patch.object(mta_custom, "_load_existing_mta_cache", return_value={}):
                with patch.object(mta_custom, "_parse_jina_total_pages", return_value=2):
                    with patch.object(mta_custom, "_fetch_jina_detail", return_value={}):
                        with self.assertRaisesRegex(RuntimeError, "no MTA cache"):
                            mta_custom._scrape_mta_jina(AGENCY)

    def test_ci_scrape_tries_browser_before_jina_after_direct_block(self):
        response = requests.Response()
        response.status_code = 403
        error = requests.HTTPError("blocked", response=response)

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with patch.object(mta_custom, "_scrape_mta_requests", side_effect=error):
                with patch.object(mta_custom, "_scrape_mta_browser", return_value=[CACHED_JOB]) as browser:
                    with patch.object(mta_custom, "_scrape_mta_jina") as jina:
                        jobs = mta_custom.scrape_mta(AGENCY)

        self.assertEqual(jobs, [CACHED_JOB])
        browser.assert_called_once_with(AGENCY)
        jina.assert_not_called()

    def test_ci_scrape_tries_browser_after_direct_connection_error(self):
        error = requests.ConnectionError("dns failed")

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with patch.object(mta_custom, "_scrape_mta_requests", side_effect=error):
                with patch.object(mta_custom, "_scrape_mta_browser", return_value=[CACHED_JOB]) as browser:
                    with patch.object(mta_custom, "_scrape_mta_jina") as jina:
                        jobs = mta_custom.scrape_mta(AGENCY)

        self.assertEqual(jobs, [CACHED_JOB])
        browser.assert_called_once_with(AGENCY)
        jina.assert_not_called()

    def test_ci_scrape_falls_back_to_jina_if_browser_fails(self):
        response = requests.Response()
        response.status_code = 403
        error = requests.HTTPError("blocked", response=response)

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with patch.object(mta_custom, "_scrape_mta_requests", side_effect=error):
                with patch.object(mta_custom, "_scrape_mta_browser", side_effect=RuntimeError("browser failed")):
                    with patch.object(mta_custom, "_scrape_mta_jina", return_value=[CACHED_JOB]) as jina:
                        jobs = mta_custom.scrape_mta(AGENCY)

        self.assertEqual(jobs, [CACHED_JOB])
        jina.assert_called_once_with(AGENCY)

    def test_loads_mta_cache_from_actions_cache_and_checked_in_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            thin_cache = Path(tmpdir, "actions-cache.csv")
            rich_baseline = Path(tmpdir, "baseline.csv")
            pd.DataFrame(
                [
                    {
                        "agency": "MTA",
                        "source_url": "https://careers.mta.org/jobs/shared",
                        "title": "Shared",
                        "salary_text": "",
                    }
                ]
            ).to_csv(thin_cache, index=False)
            pd.DataFrame(
                [
                    {
                        "agency": "MTA",
                        "source_url": "https://careers.mta.org/jobs/shared",
                        "title": "Shared",
                        "salary_text": "$100,000",
                        "all_meaningful_info": "Salary Range: $100,000",
                    },
                    {
                        "agency": "MTA",
                        "source_url": "https://careers.mta.org/jobs/baseline-only",
                        "title": "Baseline Only",
                        "salary_text": "$120,000",
                    },
                ]
            ).to_csv(rich_baseline, index=False)

            with patch.dict(os.environ, {"SCRAPER_CACHE_PATHS": os.pathsep.join([str(thin_cache), str(rich_baseline)])}):
                cache = mta_custom._load_existing_mta_cache(AGENCY)

        self.assertIn("https://careers.mta.org/jobs/baseline-only", cache)
        self.assertEqual(cache["https://careers.mta.org/jobs/shared"]["salary_text"], "$100,000")

    def test_repairs_stale_cached_mta_salary_text_from_context(self):
        details = mta_custom._cached_job_details(STALE_CACHED_DIRECTOR)

        self.assertEqual(details["salary_text"], "$129,446 to $161,807")

    def test_repairs_split_cached_mta_salary_text(self):
        details = mta_custom._cached_job_details(SPLIT_CACHED_DIRECTOR)

        self.assertEqual(details["salary_text"], "$129,446 to $161,807")


if __name__ == "__main__":
    unittest.main()
