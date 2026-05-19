import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_preserves_failed_small_agency_cache(self):
        current = pd.DataFrame([{"job_id": "pace-1", "agency": "Pace", "title": "Operator"}])
        previous = pd.DataFrame([{"job_id": "samtrans-1", "agency": "SamTrans", "title": "Planner"}])
        scrape_results = [
            {
                "agency": "SamTrans",
                "platform": "governmentjobs",
                "jobs": [],
                "elapsed": 11,
                "error": "ConnectTimeout",
            }
        ]

        merged = main._preserve_failed_agency_cache(current, previous, scrape_results)

        self.assertEqual(int((merged["agency"] == "SamTrans").sum()), 1)
        self.assertEqual(int((merged["agency"] == "Pace").sum()), 1)

    def test_preserves_partial_mta_cache(self):
        current = pd.DataFrame([{"job_id": f"mta-{index}", "agency": "MTA"} for index in range(2)])
        previous = pd.DataFrame([{"job_id": f"mta-{index}", "agency": "MTA"} for index in range(4)])

        with patch.dict(
            os.environ,
            {
                "SCRAPER_PARTIAL_AGENCY_CACHE_MIN": "1",
                "SCRAPER_AGENCY_MIN_TOTAL_RATIO": "0.75",
                "SCRAPER_PARTIAL_CACHE_AGENCIES": "MTA",
            },
        ):
            merged = main._preserve_partial_agency_cache(current, previous)

        self.assertEqual(int((merged["agency"] == "MTA").sum()), 6)

    def test_dedupe_prefers_cached_row_with_salary_details(self):
        rows = pd.DataFrame(
            [
                {
                    "job_id": "mta-1",
                    "agency": "MTA",
                    "title": "Director Project Management",
                    "salary_text": "",
                    "description": "",
                },
                {
                    "job_id": "mta-1",
                    "agency": "MTA",
                    "title": "Director Project Management",
                    "salary_text": "$115,000 - $145,000",
                    "description": "Detailed cached description",
                },
            ]
        )

        deduped = main._dedupe_jobs_by_quality(rows)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped.iloc[0]["salary_text"], "$115,000 - $145,000")

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

    def test_load_previous_output_merges_actions_cache_with_checked_in_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir, "cache.csv")
            baseline_path = Path(tmpdir, "baseline.csv")
            pd.DataFrame(
                [
                    {
                        "job_id": "same",
                        "agency": "MTA",
                        "title": "Cached Thin",
                        "source_url": "https://example.com/same",
                        "salary_text": "",
                    }
                ]
            ).to_csv(cache_path, index=False)
            pd.DataFrame(
                [
                    {
                        "job_id": "same",
                        "agency": "MTA",
                        "title": "Baseline Rich",
                        "source_url": "https://example.com/same",
                        "salary_text": "$100,000",
                        "description": "Detailed row",
                    },
                    {
                        "job_id": "baseline-only",
                        "agency": "MTA",
                        "title": "Baseline Only",
                        "source_url": "https://example.com/baseline-only",
                        "salary_text": "$120,000",
                    },
                ]
            ).to_csv(baseline_path, index=False)

            with patch.dict(os.environ, {"SCRAPER_CACHE_PATHS": os.pathsep.join([str(cache_path), str(baseline_path)])}):
                previous = main._load_previous_output(Path(tmpdir, "missing.csv"))

        self.assertEqual(len(previous), 2)
        self.assertEqual(previous[previous["job_id"] == "same"].iloc[0]["salary_text"], "$100,000")


if __name__ == "__main__":
    unittest.main()
