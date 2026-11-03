"""Feature extraction logic shared between training and live API inference."""

from typing import Dict, List, Sequence, Union
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
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


def extract_cyclical_features(timestamp: pd.Timestamp) -> Dict[str, float]:
    """Compute cyclical sine/cosine encodings and calendar features."""
    hour = timestamp.hour
    month = timestamp.month
    day_of_week = timestamp.dayofweek

    return {
        "hour_sin": float(np.sin(2 * np.pi * hour / 24.0)),
        "hour_cos": float(np.cos(2 * np.pi * hour / 24.0)),
        "month_sin": float(np.sin(2 * np.pi * month / 12.0)),
        "month_cos": float(np.cos(2 * np.pi * month / 12.0)),
        "day_of_week": int(day_of_week),
        "day_of_month": int(timestamp.day),
        "day_of_year": int(timestamp.dayofyear),
        "is_weekend": int(day_of_week >= 5),
    }


def make_features_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Batch feature creation for training or evaluation DataFrame."""
    ts = pd.to_datetime(frame["timestamp"], errors="coerce")
    out = pd.DataFrame(index=frame.index)

    hour = ts.dt.hour
    month = ts.dt.month
    day_of_week = ts.dt.dayofweek

    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    out["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    out["day_of_week"] = day_of_week
    out["day_of_month"] = ts.dt.day
    out["day_of_year"] = ts.dt.dayofyear
    out["is_weekend"] = (day_of_week >= 5).astype(int)

    # Lags & rolling
    cons = frame["consumption_kwh"]
    out["lag_1"] = cons.shift(1)
    out["lag_24"] = cons.shift(24)
    out["lag_168"] = cons.shift(168).bfill().fillna(out["lag_24"])
    out["rolling_mean_24"] = cons.shift(1).rolling(24).mean()

    return out[FEATURE_COLUMNS]


def extract_single_feature_vector(
    timestamp: pd.Timestamp,
    lag_1: float,
    lag_24: float,
    lag_168: float,
    rolling_mean_24: float,
) -> List[float]:
    """Lightweight feature extraction for high-speed live inference without DataFrame overhead."""
    hour = timestamp.hour
    month = timestamp.month
    day_of_week = timestamp.dayofweek

    return [
        float(np.sin(2 * np.pi * hour / 24.0)),
        float(np.cos(2 * np.pi * hour / 24.0)),
        float(np.sin(2 * np.pi * month / 12.0)),
        float(np.cos(2 * np.pi * month / 12.0)),
        float(day_of_week),
        float(timestamp.day),
        float(timestamp.dayofyear),
        float(1.0 if day_of_week >= 5 else 0.0),
        float(lag_1),
        float(lag_24),
        float(lag_168),
        float(rolling_mean_24),
    ]
