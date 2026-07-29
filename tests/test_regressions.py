from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import data_source  # noqa: E402
import metrics  # noqa: E402


class TearsheetRegressionTests(unittest.TestCase):
    def test_year_chunks_never_cross_calendar_year(self):
        self.assertEqual(
            data_source.year_chunks("20240103", "20260721"),
            [
                ("20240103", "20241231"),
                ("20250101", "20251231"),
                ("20260101", "20260721"),
            ],
        )

    def test_fund_nav_uses_fund_daily_and_deduplicates_dates(self):
        ds = data_source.DataSource(prefer="sample")
        with patch.object(
            ds,
            "fetch",
            side_effect=[
                [{"symbol": "510300.SH", "date": "20241231", "close": 4.0}],
                [
                    {"symbol": "510300.SH", "date": "20241231", "close": 4.0},
                    {"symbol": "510300.SH", "date": "20250102", "close": 4.1},
                ],
            ],
        ) as fetch:
            rows = ds.fund_nav("510300.SH", "20240101", "20250102")
        self.assertEqual([row["date"] for row in rows], ["20241231", "20250102"])
        self.assertTrue(all(call.args[0] == "get_fund_daily" for call in fetch.call_args_list))
        self.assertEqual(rows[-1]["unit_nav"], 4.1)

    def test_benchmark_uses_inner_join_and_contract_field(self):
        strategy = pd.Series(
            [0.01, 0.02, -0.01, 0.005],
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        )
        benchmark = pd.Series(
            [0.005, 0.01, 0.0, -0.002],
            index=pd.to_datetime(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]),
        )
        got = metrics.benchmark_stats(strategy, benchmark, 252)
        self.assertEqual(got["n_aligned"], 3)
        self.assertIn("excess_annualized_return", got)
        self.assertEqual(got["excess_annualized_return"], got["excess_annual"])

    def test_prefer_sample_still_requires_series_source(self):
        run = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "tearsheet.py"), "--prefer", "sample"],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("required", run.stderr.lower())


if __name__ == "__main__":
    unittest.main()
