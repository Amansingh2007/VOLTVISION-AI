"""Train and evaluate the electricity consumption ML model.

Uses cyclical temporal encodings and lag/rolling features.
Saves a compressed, high-performance model bundle.
"""

from pathlib import Path
import argparse
import json
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_PATH = BACKEND_DIR / "data" / "electricity.csv"
MODEL_PATH = BACKEND_DIR / "model.joblib"
METRICS_PATH = BACKEND_DIR / "metrics.json"

from ml.features import FEATURE_COLUMNS, make_features_dataframe


def train(model_type: str = "hgb") -> dict:
    if not DATA_PATH.exists():
        raise SystemExit(
            f"Dataset not found: {DATA_PATH}\n"
            "Add a real CSV with timestamp,consumption_kwh columns first. "
            "See backend/data/README.md."
        )

    print(f"Loading data from {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    required = {"timestamp", "consumption_kwh"}
    if not required.issubset(df.columns):
        raise SystemExit(f"CSV must include columns: {sorted(required)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["consumption_kwh"] = pd.to_numeric(df["consumption_kwh"], errors="coerce")
    df = df.dropna(subset=["timestamp", "consumption_kwh"])
    df = df[df["consumption_kwh"] >= 0].sort_values("timestamp")
    df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    if len(df) < 100:
        raise SystemExit("Need at least 100 clean time points for training.")

    # Resample to regular hourly intervals and interpolate small gaps
    df = (
        df.set_index("timestamp")
        .resample("h")["consumption_kwh"]
        .mean()
        .interpolate(limit=3)
        .dropna()
        .reset_index()
    )

    print("Extracting features...")
    features = make_features_dataframe(df)
    model_data = pd.concat([df[["timestamp", "consumption_kwh"]], features], axis=1).dropna().reset_index(drop=True)

    if len(model_data) < 100:
        raise SystemExit("Not enough usable rows after lag feature creation.")

    # Chronological 80/20 train/test split to avoid data leakage
    split = int(len(model_data) * 0.8)
    train_data, test_data = model_data.iloc[:split], model_data.iloc[split:]

    X_train, y_train = train_data[FEATURE_COLUMNS], train_data["consumption_kwh"]
    X_test, y_test = test_data[FEATURE_COLUMNS], test_data["consumption_kwh"]

    print(f"Training {model_type.upper()} model on {len(X_train)} hourly samples...")
    t0 = time.time()
    if model_type == "rf":
        model = RandomForestRegressor(
            n_estimators=150,
            max_depth=16,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
        )
    else:
        model = HistGradientBoostingRegressor(
            max_iter=300,
            min_samples_leaf=15,
            learning_rate=0.08,
            random_state=42,
        )

    model.fit(X_train, y_train)
    train_duration_sec = round(time.time() - t0, 3)

    pred = np.clip(model.predict(X_test), 0, None)
    mae = float(mean_absolute_error(y_test, pred))
    rmse = float(root_mean_squared_error(y_test, pred))
    r2 = float(r2_score(y_test, pred))

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "model_type": model.__class__.__name__,
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Save compressed model bundle
    joblib.dump(bundle, MODEL_PATH, compress=3)
    model_size_kb = round(os.path.getsize(MODEL_PATH) / 1024, 2)

    metrics = {
        "model": model.__class__.__name__,
        "model_size_kb": model_size_kb,
        "train_duration_sec": train_duration_sec,
        "rows": int(len(model_data)),
        "train_rows": int(len(train_data)),
        "test_rows": int(len(test_data)),
        "mae_kwh": mae,
        "rmse_kwh": rmse,
        "r2": r2,
        "test_start": str(test_data["timestamp"].min()),
        "test_end": str(test_data["timestamp"].max()),
        "feature_columns": FEATURE_COLUMNS,
        "note": "Chronological holdout metrics evaluated on hourly energy test split.",
    }

    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"\nSaved model bundle ({model_size_kb} KB) to: {MODEL_PATH}")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Train electricity consumption model")
    parser.add_argument(
        "--model",
        choices=["hgb", "rf"],
        default="hgb",
        help="Model architecture: 'hgb' (HistGradientBoosting, default) or 'rf' (RandomForest)",
    )
    args = parser.parse_args()
    train(model_type=args.model)


if __name__ == "__main__":
    main()
