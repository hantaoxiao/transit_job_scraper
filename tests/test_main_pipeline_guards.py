import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import main


class MainPipelineGuardTests(unittest.TestCase):
    def test_write_site_data_counts_string_booleans_from_cached_csv(self):
        df = pd.DataFrame(
            [
                {"agency": "MTA", "salary_is_listed": "True", "salary_is_comparable": "True", "closing_date": ""},
                {"agency": "MTA", "salary_is_listed": "False", "salary_is_comparable": "False", "closing_date": ""},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            main.write_site_data(df, Path(tmpdir))
            raw = Path(tmpdir, "data.js").read_text(encoding="utf-8")

        payload = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
        self.assertEqual(payload["agency_metrics"][0]["salary_listed_pct"], 50)
        self.assertEqual(payload["agency_metrics"][0]["comparable_salary_pct"], 50)

    def test_preserves_large_agency_cache_when_current_scrape_returns_zero(self):
        current = pd.DataFrame([{"job_id": "pace-1", "agency": "Pace", "title": "Operator"}])
        previous = pd.DataFrame(
            [{"job_id": f"mta-{index}", "agency": "MTA", "title": f"Cached {index}"} for index in range(12)]
        )

        merged = main._preserve_zero_count_agency_cache(current, previous)

        self.assertEqual(int((merged["agency"] == "MTA").sum()), 12)
        self.assertEqual(int((merged["agency"] == "Pace").sum()), 1)

    def test_does_not_publish_all_stale_cache_when_current_scrape_is_empty(self):
        previous = pd.DataFrame(
            [{"job_id": f"mta-{index}", "agency": "MTA", "title": f"Cached {index}"} for index in range(12)]
        )

        merged = main._preserve_zero_count_agency_cache(pd.DataFrame(), previous)

        self.assertTrue(merged.empty)

    def test_rejects_implausibly_small_output(self):
        current = pd.DataFrame([{"job_id": f"job-{index}", "agency": "MTA"} for index in range(99)])
        previous = pd.DataFrame([{"job_id": f"old-{index}", "agency": "MTA"} for index in range(300)])

        with self.assertRaisesRegex(RuntimeError, "Refusing to publish"):
            main._validate_output_size(current, previous)


if __name__ == "__main__":
    unittest.main()
