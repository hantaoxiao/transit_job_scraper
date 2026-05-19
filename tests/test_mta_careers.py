import unittest
from unittest.mock import patch

from scrapers import mta_custom


AGENCY = {
    "agency": "MTA",
    "city": "New York",
    "state": "NY",
    "platform": "mta_custom",
    "jobs_url": "https://careers.mta.org/search/jobs/in",
}

CAREERS_LISTING_HTML = """
<main>
  <article>
    <a href="/jobs/17601285-director-project-management">Director Project Management</a>
    <p>Job ID: 15322</p>
    <p>Location: New York, NY, United States</p>
    <p>Department: Delivery/Stations</p>
    <p>Date Posted: May 15, 2026</p>
  </article>
</main>
"""

CAREERS_JSON = {
    "current_page": 1,
    "per_page": 100,
    "total_entries": 1,
    "entries": [
        {
            "id": "17750642",
            "talemetry_job_id": "17750642",
            "permalink": "senior-director-project-management-various",
            "title": "Senior Director Project Management (Various)",
            "location": {
                "locality": "New York",
                "region_abbr": "NY",
                "country": "United States",
            },
        }
    ],
}

DETAIL_HTML = """
<main>
  <article>
    <h1>Director Project Management</h1>
    <table><tbody>
      <tr><td>JOB TITLE:</td><td>Director Project Management</td></tr>
      <tr><td>AGENCY:</td><td>Construction &amp; Development</td></tr>
      <tr><td>DEPT/DIV:</td><td>Delivery/Stations</td></tr>
      <tr><td>REPORTS TO:</td><td>Senior Director Project Management</td></tr>
      <tr><td>WORK LOCATION:</td><td>2 Broadway</td></tr>
      <tr><td>HOURS OF WORK:</td><td>8:30 AM to 5:00 PM</td></tr>
      <tr><td>JOB FAMILY: CON</td><td>GRADE: 006</td></tr>
      <tr><td>SALARY RANGE:</td><td><span>$12</span><span>9,446 </span>to <span>$1</span><span>61,807</span></td></tr>
      <tr><td>DEADLINE:</td><td>Open Until Filled</td></tr>
    </tbody></table>
    <p><strong>Summary</strong></p>
    <p>The Director Project Management is responsible for capital project delivery.</p>
  </article>
</main>
"""

JSON_LD_DETAIL_HTML = """
<main>
  <article>
    <h1>Senior Director Project Management (Various)</h1>
    <script type="application/ld+json">
      {
        "@context": "http://schema.org/",
        "@type": "JobPosting",
        "title": "Senior Director Project Management (Various)",
        "description": "<p>JOB TITLE: Senior Director, Project Management</p><p>AGENCY: Construction &amp; Development</p><p>SALARY RANGE: $149,247 to $186,559</p><p>DEADLINE: Open Until Filled</p>",
        "identifier": {"@type": "PropertyValue", "name": "MTA Careers Site", "value": "15861"},
        "datePosted": "2026-05-18",
        "validThrough": "",
        "jobLocation": {
          "@type": "Place",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "2 Broadway",
            "addressLocality": "New York",
            "addressRegion": "New York",
            "addressCountry": "United States"
          }
        }
      }
    </script>
  </article>
</main>
"""

HOURLY_DETAIL_TEXT = """
Salary Range:
The current minimum salary for Senior Stationary Engineer is $ 87 . 71 per hour
for a 40-hour week.
Responsibilities:
Operate and maintain equipment.
"""


class MtaCareersTests(unittest.TestCase):
    def test_parse_careers_listing_keeps_posted_date_metadata(self):
        summaries = mta_custom._parse_careers_search_page(
            CAREERS_LISTING_HTML,
            AGENCY,
            "https://careers.mta.org/search/jobs/in?page=1&per_page=100",
        )

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["mta_job_id"], "15322")
        self.assertEqual(summaries[0]["posted_date"], "May 15, 2026")
        self.assertEqual(summaries[0]["posted_date_iso"], "2026-05-15")
        self.assertEqual(summaries[0]["department"], "Delivery/Stations")
        self.assertEqual(
            summaries[0]["source_url"],
            "https://careers.mta.org/jobs/17601285-director-project-management",
        )

    def test_parse_careers_json_listing_uses_ci_safe_feed(self):
        summaries = mta_custom._parse_careers_search_json(CAREERS_JSON, AGENCY)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["mta_internal_id"], "17750642")
        self.assertEqual(summaries[0]["title"], "Senior Director Project Management (Various)")
        self.assertEqual(summaries[0]["location"], "New York, NY, United States")
        self.assertEqual(
            summaries[0]["source_url"],
            "https://careers.mta.org/jobs/17750642-senior-director-project-management-various",
        )

    def test_parse_careers_detail_repairs_split_mta_salary(self):
        details = mta_custom._parse_detail_page(DETAIL_HTML)

        self.assertEqual(details["salary_text"], "$129,446 to $161,807")
        self.assertEqual(details["business_unit"], "Construction & Development")
        self.assertEqual(details["department"], "Delivery/Stations")
        self.assertEqual(details["closing_date"], "Open Until Filled")

    def test_parse_careers_detail_uses_json_ld_posted_date_and_identifier(self):
        details = mta_custom._parse_detail_page(JSON_LD_DETAIL_HTML)

        self.assertEqual(details["mta_job_id"], "15861")
        self.assertEqual(details["requisition_id"], "15861")
        self.assertEqual(details["posted_date"], "2026-05-18")
        self.assertEqual(details["detail_location"], "New York, NY, United States")
        self.assertEqual(details["salary_text"], "$149,247 to $186,559")

    def test_location_parser_strips_zip_from_state(self):
        city, state = mta_custom._location_to_city_state("New York, NY 10004, United States", AGENCY)

        self.assertEqual(city, "New York")
        self.assertEqual(state, "NY")

    def test_location_parser_handles_state_name_with_zip(self):
        city, state = mta_custom._location_to_city_state("Queens, New York 11377, United States", AGENCY)

        self.assertEqual(city, "Queens")
        self.assertEqual(state, "NY")

    def test_location_parser_handles_city_state_without_comma(self):
        city, state = mta_custom._location_to_city_state("East New York - 25 Jamaica Ave, Brooklyn NY", AGENCY)

        self.assertEqual(city, "Brooklyn")
        self.assertEqual(state, "NY")

    def test_location_parser_handles_city_state_zip_without_comma(self):
        city, state = mta_custom._location_to_city_state("130 Livingston Street, 7 th Floor, Brooklyn NY 11201", AGENCY)

        self.assertEqual(city, "Brooklyn")
        self.assertEqual(state, "NY")

    def test_location_parser_handles_borough_locality_as_new_york(self):
        city, state = mta_custom._location_to_city_state("2 Broadway, Manhattan", AGENCY)

        self.assertEqual(city, "Manhattan")
        self.assertEqual(state, "NY")

    def test_location_parser_handles_bare_zip_as_agency_state(self):
        city, state = mta_custom._location_to_city_state("10001", AGENCY)

        self.assertEqual(city, "New York")
        self.assertEqual(state, "NY")

    def test_location_parser_forces_all_mta_rows_to_new_york_state(self):
        city, state = mta_custom._location_to_city_state("Newark, NJ, United States", AGENCY)

        self.assertEqual(city, "Newark")
        self.assertEqual(state, "NY")

    def test_careers_detail_preserves_hourly_salary_context(self):
        salary = mta_custom._salary_from_detail({}, HOURLY_DETAIL_TEXT)

        self.assertEqual(
            salary,
            "The current minimum salary for Senior Stationary Engineer is $87.71 per hour",
        )

    def test_scrape_mta_uses_careers_listing_and_detail_only(self):
        detail = mta_custom._parse_detail_page(DETAIL_HTML)
        summary = mta_custom._parse_careers_search_page(
            CAREERS_LISTING_HTML,
            AGENCY,
            "https://careers.mta.org/search/jobs/in?page=1&per_page=100",
        )[0]

        with patch.object(mta_custom, "_scrape_careers_summaries", return_value=[summary]):
            with patch.object(mta_custom, "cached_job", return_value={}):
                with patch.object(mta_custom, "has_cached_detail", return_value=False):
                    with patch.object(mta_custom, "_fetch_detail", return_value=detail) as fetch_detail:
                        jobs = mta_custom.scrape_mta(AGENCY)

        self.assertEqual(len(jobs), 1)
        fetch_detail.assert_called_once_with("https://careers.mta.org/jobs/17601285-director-project-management")
        job = jobs[0]
        self.assertEqual(job["source_url"], "https://careers.mta.org/jobs/17601285-director-project-management")
        self.assertEqual(job["salary_range_display"], "$129,446 - $161,807")
        self.assertEqual(job["posted_date"], "May 15, 2026")
        self.assertEqual(job["mta_job_id"], "15322")
        self.assertEqual(job["requisition_id"], "15322")

    def test_no_interactive_or_external_mta_fallbacks_are_defined(self):
        self.assertFalse(hasattr(mta_custom, "_scrape_mta_browser"))
        self.assertFalse(hasattr(mta_custom, "_scrape_mta_jina"))

    def test_repairs_stale_cached_director_salary_text_from_context(self):
        details = mta_custom._cached_job_details(
            {
                "salary_text": "$12",
                "all_meaningful_info": (
                    "Director Project Management JOB FAMILY: CON GRADE: 006 "
                    "SALARY RANGE : $12 9,446 to $1 61,807 DEADLINE: Open Until Filled"
                ),
            }
        )

        self.assertEqual(details["salary_text"], "$129,446 to $161,807")


if __name__ == "__main__":
    unittest.main()
