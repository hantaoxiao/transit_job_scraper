import unittest

from scrapers import browser_jobboard


AGENCY = {
    "agency": "PATH",
    "city": "Jersey City",
    "state": "NJ",
    "platform": "panynj_custom",
    "jobs_url": "https://www.jointheportauthority.com/jobs/search?per_page=100",
}


def _path_block(index: int, *, department: str = "Rail Transit") -> str:
    department_line = f"Department: {department}\n\n" if department else ""
    return f"""
Job Title: [PATH Position {index}](https://www.jointheportauthority.com/jobs/1775{index:04d}-path-position-{index})

Job ID: 64{index:03d}

Job Family: Operations

{department_line}Location: Jersey City, NJ
"""


class PanynjPathTests(unittest.TestCase):
    def test_path_html_parser_uses_direct_listing_with_titles(self):
        html = """
        <div class="jobs__list-item">
          <div>Job Title: <a href="https://www.jointheportauthority.com/jobs/17760772-benefits">Benefits Operations and Systems Supervisor</a></div>
          <div>Job ID:</div><div>64397</div>
          <div>Job Family:</div><div>Corporate</div>
          <div>Department:</div><div>Human Resources</div>
          <div>Location:</div><div>New York,</div><div>NY</div>
        </div>
        """

        entries = browser_jobboard._parse_panynj_listing_html(html, AGENCY)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Benefits Operations and Systems Supervisor")
        self.assertEqual(entries[0]["job_id"], "64397")
        self.assertEqual(entries[0]["family"], "Corporate")
        self.assertEqual(entries[0]["department"], "Human Resources")
        self.assertEqual(entries[0]["city"], "New York")
        self.assertEqual(entries[0]["state"], "NY")

    def test_path_parser_collects_all_21_listing_blocks(self):
        markdown = "\n".join(_path_block(index) for index in range(1, 22))

        entries = browser_jobboard._parse_panynj_listing_markdown(markdown, AGENCY)

        self.assertEqual(len(entries), 21)
        self.assertEqual(entries[0]["title"], "PATH Position 1")
        self.assertEqual(entries[-1]["job_id"], "64021")

    def test_path_parser_does_not_drop_listing_when_department_is_missing(self):
        markdown = _path_block(1, department="")

        entries = browser_jobboard._parse_panynj_listing_markdown(markdown, AGENCY)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["department"], "")
        self.assertEqual(entries[0]["city"], "Jersey City")
        self.assertEqual(entries[0]["state"], "NJ")


if __name__ == "__main__":
    unittest.main()
