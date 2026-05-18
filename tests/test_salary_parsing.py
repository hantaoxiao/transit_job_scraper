import unittest

from normalizer import extract_salary, parse_salary, repair_split_money
from scrapers.mta_custom import _extract_labeled_section


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


if __name__ == "__main__":
    unittest.main()
