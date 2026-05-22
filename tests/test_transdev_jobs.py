import unittest
from unittest.mock import patch

from scrapers import browser_jobboard


AGENCY = {
    "agency": "NICE Bus",
    "city": "Garden City",
    "state": "NY",
    "platform": "transdev",
    "jobs_url": "https://transdevna.jobs/jobs/?location=Garden+City%2C+NY",
}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TransdevJobsTests(unittest.TestCase):
    def test_transdev_api_entries_use_direct_jobsyn_search(self):
        payload = {
            "jobs": [
                {
                    "title_exact": "Paratransit Operations Manager",
                    "title_slug": "paratransit-operations-manager",
                    "guid": "3D647F0E660E4582B64486713EAA2BC1",
                    "reqid": "8126",
                    "location_exact": "Garden City, NY",
                    "description": "Competitive compensation $90,000 to $105,000/year",
                    "job_category": "Operations Management & Supervisory",
                    "job_type": "Full Time",
                    "date_new": "2026-05-13T17:49:42Z",
                }
            ]
        }

        with patch.object(browser_jobboard.requests, "get", return_value=FakeResponse(payload)) as get:
            entries, ok = browser_jobboard._transdev_api_entries(AGENCY)

        self.assertTrue(ok)
        self.assertEqual(len(entries), 1)
        self.assertIn("prod-search-api.jobsyn.org", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["headers"]["X-Origin"], "transdevna.jobs")
        self.assertEqual(get.call_args.kwargs["params"]["location"], "Garden City, NY")
        self.assertEqual(entries[0]["title"], "Paratransit Operations Manager")
        self.assertEqual(entries[0]["city"], "Garden City")
        self.assertEqual(entries[0]["state"], "NY")
        self.assertEqual(entries[0]["salary_text"], "$90,000 to $105,000")
        self.assertEqual(entries[0]["requisition_id"], "8126")
        self.assertEqual(
            entries[0]["source_url"],
            "https://transdevna.jobs/paratransit-operations-manager/3D647F0E660E4582B64486713EAA2BC1/job/",
        )

    def test_transdev_scraper_raises_when_api_and_fallback_are_unparsable(self):
        with patch.object(browser_jobboard, "_transdev_api_entries", return_value=([], False)):
            with patch.object(browser_jobboard, "_transdev_jina_entries", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "Transdev listing returned no parsable jobs"):
                    browser_jobboard._scrape_transdev_jobs(AGENCY)


if __name__ == "__main__":
    unittest.main()
