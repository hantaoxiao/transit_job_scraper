import unittest
from unittest.mock import Mock, patch

from agencies import AGENCIES
from scrapers import governmentjobs, oracle


class AgencyBoardMigrationTests(unittest.TestCase):
    def agency(self, name):
        return next(agency for agency in AGENCIES if agency["agency"] == name)

    def test_mbta_requests_new_board_and_keeps_official_job_links(self):
        html = '''<li class="list-item"><a href="/careers/mbtama/jobs/5534000/planning-analyst">Planning Analyst</a>
        <ul class="list-meta"><li>Boston, MA</li><li>Full-Time - $80,000.00 Annually</li></ul></li>'''
        response = Mock(text=html)
        with patch.object(governmentjobs, "_get_with_retries", return_value=response) as get:
            with patch.object(governmentjobs, "AGENCY_DELAY", 0), patch.object(governmentjobs, "FETCH_DETAILS", False):
                jobs = governmentjobs.scrape_governmentjobs(self.agency("MBTA"))
        self.assertEqual(get.call_args.kwargs["params"]["agency"], "mbtama")
        self.assertEqual(len(jobs), 1)
        self.assertIn("/careers/mbtama/jobs/", jobs[0]["source_url"])

    def test_wmata_uses_oracle_site_and_preserves_maryland_location(self):
        agency = self.agency("WMATA")
        self.assertEqual(agency["platform"], "oracle")
        response = Mock()
        response.json.return_value = {"items": [{"requisitionList": [{
            "Id": "260123", "Title": "Rail Schedule Analyst", "PrimaryLocation": "Hyattsville, MD, United States",
        }]}]}
        session = Mock()
        session.get.return_value = response
        detail = {
            "ExternalDescriptionStr": "<p>Analyze rail schedules.</p>",
            "workLocation": [{"TownOrCity": "Hyattsville", "Region2": "Maryland"}],
            "ExternalPostedStartDate": "2026-11-09",
        }
        with patch.object(oracle.requests, "Session", return_value=session):
            with patch.object(oracle, "cached_job", return_value={}), patch.object(oracle, "_fetch_detail", return_value=detail):
                jobs = oracle.scrape_oracle(agency)
        listing_url = session.get.call_args.args[0]
        self.assertIn("eservice.wmata.com/hcmRestApi/", listing_url)
        self.assertIn("CX_2011", listing_url)
        self.assertEqual(len(jobs), 1)
        self.assertEqual((jobs[0]["city"], jobs[0]["state"]), ("Hyattsville", "MD"))
        self.assertEqual(jobs[0]["source_url"], "https://eservice.wmata.com/hcmUI/CandidateExperience/en/sites/CX_2011/job/260123")
        self.assertEqual(jobs[0]["description"], "Analyze rail schedules.")

    def test_oracle_locations_keep_dc_and_virginia(self):
        agency = self.agency("WMATA")
        self.assertEqual(oracle._city_state("Alexandria, Virginia, United States", agency), ("Alexandria", "VA"))
        self.assertEqual(oracle._city_state("Washington, District of Columbia, United States", agency), ("Washington", "DC"))
        self.assertEqual(oracle._city_state("", agency), ("Washington", "DC"))


if __name__ == "__main__":
    unittest.main()
