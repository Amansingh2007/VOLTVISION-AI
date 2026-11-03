"""Optional helper for the UCI Individual Household Electric Power Consumption file.

Download/extract the UCI file, then pass its household_power_consumption.txt path:
    python ml/prepare_uci_dataset.py path/to/household_power_consumption.txt

This dataset's Global_active_power is kW averaged over a one-minute interval.
The helper converts it to approximate kWh per minute and sums to hourly kWh.
"""
from pathlib import Path
import sys
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT = BACKEND_DIR / "data" / "electricity.csv"

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python ml/prepare_uci_dataset.py path/to/household_power_consumption.txt")
    src = Path(sys.argv[1])
    if not src.exists():
        raise SystemExit(f"File not found: {src}")
    df = pd.read_csv(src, sep=";", na_values=["?"], low_memory=False)
    required = {"Date", "Time", "Global_active_power"}
    if not required.issubset(df.columns):
        raise SystemExit(f"Expected columns: {sorted(required)}")
    df["timestamp"] = pd.to_datetime(df["Date"] + " " + df["Time"], dayfirst=True, errors="coerce")
    df["power_kw"] = pd.to_numeric(df["Global_active_power"], errors="coerce")
    df = df.dropna(subset=["timestamp", "power_kw"])
    df["minute_kwh"] = df["power_kw"] / 60.0
    hourly = df.set_index("timestamp")["minute_kwh"].resample("h").sum(min_count=1).dropna()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    hourly.rename("consumption_kwh").to_frame().reset_index().to_csv(OUT, index=False)
    print(f"Saved {len(hourly)} hourly readings to {OUT}")

if __name__ == "__main__":
    main()
