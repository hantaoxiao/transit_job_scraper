import unittest

from normalizer import extract_salary, normalize_job, parse_salary, repair_split_money, salary_search_context
from scrapers.mta_custom import _clean_compensation_section, _extract_labeled_section


class SalaryParsingTests(unittest.TestCase):
    def test_repairs_mta_split_money_tokens(self):
        text = "SALARY RANGE : $12 9,446 to $1 61,807 DEADLINE: Open Until Filled"

        self.assertEqual(
            extract_salary(text),
            "$129,446 to $161,807",
        )
        self.assertEqual(parse_salary(extract_salary(text))["salary_range_display"], "$129,446 - $161,807")

    def test_repairs_mta_single_digit_leading_split(self):
        salary = repair_split_money("$ 1 10,694 - $ 138,367")

        self.assertEqual(salary, "$110,694 - $138,367")
        self.assertEqual(parse_salary(salary)["salary_range_display"], "$110,694 - $138,367")

    def test_repairs_incomplete_comma_group(self):
        salary = extract_salary("SALARY RANGE: $156,4 76 - $184,692 DEPT/DIV: Information Technology")

        self.assertEqual(salary, "$156,476 - $184,692")
        self.assertEqual(parse_salary(salary)["salary_min"], 156476.0)

    def test_preserves_mta_hourly_context_for_current_minimum_salary(self):
        salary = extract_salary(
            "Salary Range: The current minimum salary for Senior Stationary Engineer "
            "is $ 87 . 71 per hour for a 40-hour week."
        )
        parsed = parse_salary(salary)

        self.assertEqual(salary, "The current minimum salary for Senior Stationary Engineer is $87.71 per hour")
        self.assertEqual(parsed["salary_range_display"], "$87.71/hr")
        self.assertEqual(parsed["salary_unit"], "hourly")

    def test_mta_multiline_salary_section(self):
        detail_text = "\n".join(
            [
                "SALARY RANGE",
                ":",
                "$12",
                "9,446",
                "to",
                "$1",
                "61,807",
                "DEADLINE:",
                "Open Until Filled",
            ]
        )

        self.assertEqual(
            repair_split_money(_extract_labeled_section(detail_text, "Salary Range")),
            "$129,446 to $161,807",
        )

    def test_monthly_salary_is_annualized_for_comparison(self):
        parsed = parse_salary("Full-Time Permanent - $6,535.00 - $7,485.00 Monthly")

        self.assertEqual(parsed["salary_unit"], "monthly")
        self.assertEqual(parsed["salary_range_display"], "$6,535/mo - $7,485/mo")
        self.assertEqual(parsed["salary_annual_min_est"], 78420)
        self.assertEqual(parsed["salary_annual_max_est"], 89820)

    def test_sign_on_bonus_is_not_treated_as_salary(self):
        self.assertEqual(extract_salary("Bus Operator - CapMetro($4,000 Sign-On Bonus)"), "")

    def test_normalizer_discards_bonus_that_arrives_as_salary_text(self):
        job = normalize_job(
            title="Facilities Maintenance Mechanic *$3,000 Service Bonus*",
            agency="Hampton Roads Transit",
            city="Hampton",
            state="VA",
            source_url="https://example.com/job",
            platform="workday",
            salary_text="$3,000",
            raw_context="Facilities Maintenance Mechanic *$3,000 Service Bonus* Hampton, VA Posted 30+ Days Ago",
        )

        self.assertFalse(job["salary_is_listed"])
        self.assertEqual(job["salary_unit"], "unknown")

    def test_salary_search_context_keeps_relevant_window_from_long_description(self):
        text = (
            "Overview "
            + ("general responsibilities " * 600)
            + "Compensation: Minimum: $100,256 Midpoint: $130,318 Maximum: $160,394 "
            + ("benefits and qualifications " * 600)
        )

        context = salary_search_context(text, max_length=2000)

        self.assertLess(len(context), len(text))
        self.assertIn("Minimum: $100,256", context)
        self.assertEqual(parse_salary(extract_salary(context))["salary_range_display"], "$100,256 - $160,394")

    def test_mta_compensation_section_stops_before_description_headings(self):
        salary = _clean_compensation_section(
            "Computer Associate (Operations) I: $68,468 Computer Associate (Software) II: $102,348 "
            "Responsibilities Preparing concise status updates and monthly reports. "
            "Other Information financial disclosure threshold $105,472"
        )
        parsed = parse_salary(salary)

        self.assertNotIn("Responsibilities", salary)
        self.assertEqual(parsed["salary_unit"], "annual")
        self.assertEqual(parsed["salary_annual_max_est"], 102348)


if __name__ == "__main__":
    unittest.main()
