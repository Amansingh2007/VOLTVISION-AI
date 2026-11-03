"""Unit tests for feature engineering and cyclical encodings."""

import unittest
import numpy as np
import pandas as pd
from ml.features import (
    FEATURE_COLUMNS,
    extract_cyclical_features,
    extract_single_feature_vector,
    make_features_dataframe,
)


class TestFeatureLogic(unittest.TestCase):
    def test_feature_columns_defined(self):
        expected = [
            "hour_sin",
            "hour_cos",
            "month_sin",
            "month_cos",
            "day_of_week",
            "day_of_month",
            "day_of_year",
            "is_weekend",
            "lag_1",
            "lag_24",
            "lag_168",
            "rolling_mean_24",
        ]
        self.assertEqual(FEATURE_COLUMNS, expected)

    def test_cyclical_bounds(self):
        ts = pd.Timestamp("2024-07-15 12:00:00")
        feats = extract_cyclical_features(ts)

        self.assertAlmostEqual(feats["hour_sin"], 0.0, places=5)
        self.assertAlmostEqual(feats["hour_cos"], -1.0, places=5)
        self.assertEqual(feats["day_of_week"], 0)  # Monday
        self.assertEqual(feats["is_weekend"], 0)

        # Check bounds for all hours
        for h in range(24):
            t = pd.Timestamp(f"2024-01-01 {h:02d}:00:00")
            f = extract_cyclical_features(t)
            self.assertTrue(-1.0 <= f["hour_sin"] <= 1.0)
            self.assertTrue(-1.0 <= f["hour_cos"] <= 1.0)

    def test_weekend_detection(self):
        saturday = pd.Timestamp("2024-06-01 10:00:00")  # Saturday
        sunday = pd.Timestamp("2024-06-02 10:00:00")  # Sunday
        monday = pd.Timestamp("2024-06-03 10:00:00")  # Monday

        self.assertEqual(extract_cyclical_features(saturday)["is_weekend"], 1)
        self.assertEqual(extract_cyclical_features(sunday)["is_weekend"], 1)
        self.assertEqual(extract_cyclical_features(monday)["is_weekend"], 0)

    def test_batch_dataframe_feature_creation(self):
        timestamps = pd.date_range("2024-01-01", periods=200, freq="h")
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "consumption_kwh": [1.5] * 200,
            }
        )
        features = make_features_dataframe(df)

        self.assertEqual(list(features.columns), FEATURE_COLUMNS)
        self.assertEqual(len(features), 200)

        # After row 168, lag_168 should match 1.5
        self.assertAlmostEqual(features["lag_168"].iloc[170], 1.5)
        self.assertAlmostEqual(features["rolling_mean_24"].iloc[25], 1.5)

    def test_single_feature_vector_alignment(self):
        ts = pd.Timestamp("2024-03-10 15:00:00")
        vec = extract_single_feature_vector(
            timestamp=ts,
            lag_1=2.1,
            lag_24=1.8,
            lag_168=1.9,
            rolling_mean_24=2.0,
        )

        self.assertEqual(len(vec), len(FEATURE_COLUMNS))
        self.assertEqual(vec[8], 2.1)  # lag_1
        self.assertEqual(vec[9], 1.8)  # lag_24
        self.assertEqual(vec[10], 1.9)  # lag_168
        self.assertEqual(vec[11], 2.0)  # rolling_mean_24


if __name__ == "__main__":
    unittest.main()
