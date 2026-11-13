import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from agencies import AGENCIES
from scrapers import oracle
from normalizer import normalize_job


AGENCY = next(agency for agency in AGENCIES if agency["agency"] == "NJ Transit")


class NjTransitTests(unittest.TestCase):
    def test_serviceperson_hourly_rate_does_not_include_signing_bonuses(self):
        html = '''<p>At NJ TRANSIT you will enjoy a competitive salary and excellent benefit package!</p>
        <p>$6,000 Signing Bonus for CDL A or B License Holders</p>
        <p>$3,000 Signing Bonus for all newly hired Servicepersons</p><p>$22.29 Hourly</p>'''
        description = oracle._strip_html(html)
        salary = oracle._salary_from_detail({"ExternalDescriptionStr": html}, description)
        job = normalize_job(title="Bus Serviceperson", agency="NJ Transit", city="Newark", state="NJ",
            source_url="https://jobs.njtransit.com/en/sites/Careers/job/100244", platform="oracle",
            salary_text=salary, description=description, raw_context=description)
        self.assertEqual(job["salary_range_display"], "$22.29/hr")
        self.assertEqual(job["salary_unit"], "hourly")

    def test_statewide_nj_jobs_do_not_use_state_abbreviation_as_a_city(self):
        self.assertEqual(oracle._city_state("NJ, United States", AGENCY), ("Various", "NJ"))

    def test_new_board_uses_external_api_site_and_branded_job_links(self):
        self.assertEqual(AGENCY["platform"], "oracle")
        self.assertEqual(AGENCY["site_number"], "CX_1")
        response = Mock()
        response.json.return_value = {"items": [{"TotalJobsCount": 1, "requisitionList": [{
            "Id": "12031", "Title": "Senior Director, Design Services",
            "PrimaryLocation": "Newark, NJ, United States", "PostedDate": "2026-11-12",
        }]}]}
        session = Mock()
        session.get.return_value = response
        detail = {
            "ExternalDescriptionStr": "<p>Lead design services.</p><p>Salary Range: $130,000 to $160,000 annually.</p>",
            "ExternalPostedStartDate": "2026-11-12T19:22:31+00:00",
            "workLocation": [{"TownOrCity": "Newark", "Region2": "NJ"}],
        }
        with patch.object(oracle.requests, "Session", return_value=session):
            with patch.object(oracle, "cached_job", return_value={}), patch.object(oracle, "_fetch_detail", return_value=detail) as fetch:
                jobs = oracle.scrape_oracle(AGENCY)
        listing_url = session.get.call_args.args[0]
        self.assertEqual(urlparse(listing_url).netloc, "ibrgjb.fa.ocs.oraclecloud.com")
        self.assertIn("siteNumber=CX_1", parse_qs(urlparse(listing_url).query)["finder"][0])
        self.assertEqual(fetch.call_args.args[1:], (AGENCY["api_base_url"], "CX_1", "12031"))
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["source_url"], "https://jobs.njtransit.com/en/sites/Careers/job/12031")
        self.assertEqual((job["city"], job["state"]), ("Newark", "NJ"))
        self.assertIn("Lead design services.", job["description"])
        self.assertEqual(job["salary_range_display"], "$130,000 - $160,000")
        self.assertTrue(job["posted_date"].startswith("2026-11-12"))

    def test_standard_oracle_urls_are_preserved(self):
        self.assertEqual(
            oracle._oracle_public_url("https://eservice.wmata.com", "CX_2011", "347",
                site_url="https://eservice.wmata.com/hcmUI/CandidateExperience/en/sites/CX_2011/jobs"),
            "https://eservice.wmata.com/hcmUI/CandidateExperience/en/sites/CX_2011/job/347",
        )

    def test_vanity_url_keeps_alias_and_omits_search_filters(self):
        self.assertEqual(
            oracle._oracle_public_url(AGENCY["api_base_url"], "CX_1", "12031",
                site_url=AGENCY["jobs_url"] + "?selectedPostingDatesFacet=30"),
            "https://jobs.njtransit.com/en/sites/Careers/job/12031",
        )


if __name__ == "__main__":
    unittest.main()
