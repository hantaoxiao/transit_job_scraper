import unittest

from scrapers import browser_jobboard


AGENCY = {
    "agency": "Utah Transit Authority",
    "city": "Salt Lake City",
    "state": "UT",
    "platform": "uta_custom",
    "jobs_url": "https://careers.rideuta.com/search/jobs",
}


class UtaCustomTests(unittest.TestCase):
    def test_uta_html_parser_reads_current_card_shape(self):
        html = """
        <div class="jobs-section__item padded-v-medium">
          <div class="row-- box">
            <div class="column large-4 selected">
              <div>Job ID: 26-331</div>
              <h6><a href="https://careers.rideuta.com/jobs/17598021-facilities-journeyist-class-a-technician">Facilities Journeyist-Class A Technician</a></h6>
              <div>Location:</div>
              <div>Salt Lake City,</div>
              <div>UT,</div>
              <div>United States</div>
            </div>
            <div>Date posted</div>
            <div>05.20.26</div>
            <a href="https://careers.rideuta.com/jobs/17598021-facilities-journeyist-class-a-technician">View Job</a>
          </div>
        </div>
        """

        entries = browser_jobboard._parse_uta_listing_html(html, AGENCY)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Facilities Journeyist-Class A Technician")
        self.assertEqual(entries[0]["job_id"], "26-331")
        self.assertEqual(entries[0]["posted_date"], "05.20.26")
        self.assertEqual(entries[0]["city"], "Salt Lake City")
        self.assertEqual(entries[0]["state"], "UT")

    def test_uta_markdown_parser_reads_posted_date_on_next_line(self):
        markdown = """
Job ID: 26-331

###### [Facilities Journeyist-Class A Technician](https://careers.rideuta.com/jobs/17598021-facilities-journeyist-class-a-technician)

Location:  Salt Lake City, UT, United States

Date posted

05.20.26

[View Job](https://careers.rideuta.com/jobs/17598021-facilities-journeyist-class-a-technician)
"""

        entries = browser_jobboard._parse_uta_listing_markdown(markdown, AGENCY)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["posted_date"], "05.20.26")


if __name__ == "__main__":
    unittest.main()
