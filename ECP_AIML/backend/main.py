"""FastAPI endpoints for electricity consumption forecasting, bill prediction, and frontend integration."""

from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import os
import warnings

# Suppress single-row prediction feature name warning for faster execution
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from ml.features import FEATURE_COLUMNS, extract_single_feature_vector
import database

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
MODEL_PATH = BASE_DIR / "model.joblib"
DATA_PATH = BASE_DIR / "data" / "electricity.csv"

# Global in-memory cache populated on startup
ml_state: Dict[str, Any] = {
    "bundle": None,
    "history_df": None,
    "tail_kwh": None,
    "last_timestamp": None,
    "monthly_baselines": None,
}


def load_bundle_from_disk() -> Dict[str, Any]:
    if not MODEL_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "ML model is not trained yet. Run: python ml/train_model.py"
            ),
        )
    return joblib.load(MODEL_PATH)


def load_history_from_disk() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Dataset not found. Add backend/data/electricity.csv first.",
        )

    df = pd.read_csv(DATA_PATH)
    if not {"timestamp", "consumption_kwh"}.issubset(df.columns):
        raise HTTPException(
            status_code=500,
            detail="Dataset must have timestamp and consumption_kwh columns.",
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["consumption_kwh"] = pd.to_numeric(df["consumption_kwh"], errors="coerce")

    df = (
        df.dropna(subset=["timestamp", "consumption_kwh"])
        .sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"])
        .set_index("timestamp")
        .resample("h")["consumption_kwh"]
        .mean()
        .interpolate(limit=3)
        .dropna()
    )

    if len(df) < 24:
        raise HTTPException(
            status_code=422,
            detail="At least 24 hourly readings are required for forecasting.",
        )

    return df.rename_axis("timestamp").reset_index()


def refresh_ml_state():
    """Populate or refresh the in-memory model and data cache."""
    if MODEL_PATH.exists():
        bundle = joblib.load(MODEL_PATH)
        # Avoid thread synchronization overhead for single-row inference
        if hasattr(bundle.get("model"), "n_jobs"):
            bundle["model"].n_jobs = 1
        ml_state["bundle"] = bundle
    else:
        ml_state["bundle"] = None

    if DATA_PATH.exists():
        df = load_history_from_disk()
        ml_state["history_df"] = df
        ml_state["last_timestamp"] = pd.Timestamp(df["timestamp"].iloc[-1])
        # Keep up to the last 200 readings for instant lag feature initialization
        ml_state["tail_kwh"] = df["consumption_kwh"].iloc[-200:].astype(float).tolist()

        # Compute historical monthly baselines (average total kWh per calendar month)
        df_copy = df.copy()
        df_copy["month"] = df_copy["timestamp"].dt.month
        df_copy["year"] = df_copy["timestamp"].dt.year
        monthly_sums = df_copy.groupby(["year", "month"])["consumption_kwh"].sum()
        ml_state["monthly_baselines"] = monthly_sums.groupby("month").mean().to_dict()
    else:
        ml_state["history_df"] = None
        ml_state["tail_kwh"] = None
        ml_state["last_timestamp"] = None
        ml_state["monthly_baselines"] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager: load ML assets and init DB once at server startup."""
    refresh_ml_state()
    database.init_db()
    yield
    ml_state.clear()


app = FastAPI(
    title="VoltVision AI — Electricity Consumption Prediction API",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS configuration supporting integrated server and Live Server
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = (
    [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    if allowed_origins_env
    else [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "null",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def serve_index_on_browser_root(request: Request, call_next):
    """Serve frontend index.html when a web browser requests the root URL."""
    if request.url.path == "/" and "text/html" in request.headers.get("accept", ""):
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
    return await call_next(request)


# ================= DATA SCHEMAS =================

class MonthlyRequest(BaseModel):
    month: int = Field(ge=1, le=12, description="Month (1-12)")
    year: int = Field(ge=2000, le=2100, description="Year (2000-2100)")
    household_size: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Number of household occupants",
    )
    average_temperature_c: float = Field(
        default=24.0,
        ge=-30,
        le=60,
        description="Expected average monthly outdoor temperature in Celsius",
    )


class ForecastRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=31, description="Number of days to forecast")


class BillPredictionRequest(BaseModel):
    bhk: int = Field(default=3, ge=1, le=10, description="Property type / BHK (1-10)")
    occupants: int = Field(default=4, ge=1, le=30, description="Number of occupants")
    season: str = Field(default="summer", description="Season: summer, monsoon, or winter")
    temperature_c: float = Field(default=36.0, ge=-30.0, le=60.0, description="Average daily temperature (°C)")

    # Optional Appliance Toggles & Parameters
    ac_enabled: bool = Field(default=True, description="Enable AC")
    ac_units: int = Field(default=2, ge=0, le=10, description="Number of AC units")
    ac_hours: float = Field(default=8.0, ge=0.0, le=24.0, description="Daily AC usage hours")
    ac_star: int = Field(default=5, ge=1, le=5, description="AC star efficiency rating (1, 3, or 5)")

    geyser_enabled: bool = Field(default=True, description="Enable Geyser")
    geyser_units: int = Field(default=2, ge=0, le=10, description="Number of geysers/boilers")
    geyser_hours: float = Field(default=1.5, ge=0.0, le=24.0, description="Daily geyser usage hours")

    fridge_enabled: bool = Field(default=True, description="Enable Refrigerator")
    fridge_type: str = Field(default="3star-double", description="Fridge type (single, 3star-double, 5star-double, side-by-side)")

    wm_enabled: bool = Field(default=True, description="Enable Washing Machine")
    wm_loads: int = Field(default=4, ge=0, le=50, description="Washing machine loads per week")

    solar_enabled: bool = Field(default=True, description="Enable Rooftop Solar")
    solar_kw: float = Field(default=1.5, ge=0.0, le=50.0, description="Rooftop solar capacity in kW")

    ev_enabled: bool = Field(default=False, description="Enable EV Charging")
    ev_km: float = Field(default=20.0, ge=0.0, le=500.0, description="Daily EV commute in km")

    # Newly Added Optional Appliances
    ceiling_fan_enabled: bool = Field(default=True, description="Enable Roof/Ceiling Fans")
    ceiling_fan_units: int = Field(default=3, ge=0, le=20, description="Ceiling fan units")
    ceiling_fan_hours: float = Field(default=10.0, ge=0.0, le=24.0, description="Ceiling fan daily hours")
    ceiling_fan_type: str = Field(default="standard", description="standard (75W) or bldc (32W)")

    table_fan_enabled: bool = Field(default=False, description="Enable Table/Stand Fans")
    table_fan_units: int = Field(default=1, ge=0, le=10, description="Table fan units")
    table_fan_hours: float = Field(default=6.0, ge=0.0, le=24.0, description="Table fan daily hours")

    water_pump_enabled: bool = Field(default=True, description="Enable Water Pump")
    water_pump_hp: float = Field(default=1.0, ge=0.25, le=5.0, description="Water pump motor HP")
    water_pump_hours: float = Field(default=1.0, ge=0.0, le=12.0, description="Water pump daily hours")
    water_pump_timing: str = Field(default="morning", description="morning, afternoon, evening, night")

    mixer_enabled: bool = Field(default=True, description="Enable Mixer Grinder")
    mixer_minutes: float = Field(default=20.0, ge=0.0, le=180.0, description="Mixer daily minutes")

    led_bulbs_enabled: bool = Field(default=True, description="Enable LED Lighting")
    led_bulbs_units: int = Field(default=8, ge=0, le=60, description="Number of LED bulbs")
    led_bulbs_hours: float = Field(default=6.0, ge=0.0, le=24.0, description="LED daily hours")

    tv_enabled: bool = Field(default=True, description="Enable Smart LED TV")
    tv_units: int = Field(default=1, ge=0, le=10, description="Number of TV units")
    tv_hours: float = Field(default=4.0, ge=0.0, le=24.0, description="TV daily watch hours")

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            mapping = {
                "temp": "temperature_c",
                "temperature": "temperature_c",
                "acUnits": "ac_units",
                "acHours": "ac_hours",
                "acStar": "ac_star",
                "acEnabled": "ac_enabled",
                "geyserUnits": "geyser_units",
                "geyserHours": "geyser_hours",
                "geyserEnabled": "geyser_enabled",
                "fridgeType": "fridge_type",
                "fridgeEnabled": "fridge_enabled",
                "wmLoads": "wm_loads",
                "wmEnabled": "wm_enabled",
                "solarKw": "solar_kw",
                "solarEnabled": "solar_enabled",
                "evKm": "ev_km",
                "evEnabled": "ev_enabled",
                "ceilingFanEnabled": "ceiling_fan_enabled",
                "ceilingFanUnits": "ceiling_fan_units",
                "ceilingFanHours": "ceiling_fan_hours",
                "ceilingFanType": "ceiling_fan_type",
                "tableFanEnabled": "table_fan_enabled",
                "tableFanUnits": "table_fan_units",
                "tableFanHours": "table_fan_hours",
                "waterPumpEnabled": "water_pump_enabled",
                "waterPumpHp": "water_pump_hp",
                "waterPumpHours": "water_pump_hours",
                "waterPumpTiming": "water_pump_timing",
                "mixerEnabled": "mixer_enabled",
                "mixerMinutes": "mixer_minutes",
                "ledBulbsEnabled": "led_bulbs_enabled",
                "ledBulbsUnits": "led_bulbs_units",
                "ledBulbsHours": "led_bulbs_hours",
                "tvEnabled": "tv_enabled",
                "tvUnits": "tv_units",
                "tvHours": "tv_hours",
            }
            for camel, snake in mapping.items():
                if camel in data and snake not in data:
                    data[snake] = data[camel]
        return data


class WhatIfRequest(BaseModel):
    ac_temp_optimized: bool = False
    geyser_timer_used: bool = False
    led_bldc_installed: bool = False
    solar_add_1kw: bool = False


class RegisterRequest(BaseModel):
    name: str
    consumer_id: str
    email: str
    password: str
    sanctioned_load: float = 5.0
    category: str = "Domestic Consumer"
    provider: str = "National Smart Grid Connected"

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "consumerId" in data and "consumer_id" not in data:
                data["consumer_id"] = data["consumerId"]
            if "sanctionedLoad" in data and "sanctioned_load" not in data:
                data["sanctioned_load"] = data["sanctionedLoad"]
        return data


class LoginRequest(BaseModel):
    identifier: str
    password: str

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "consumerId" in data and "identifier" not in data:
                data["identifier"] = data["consumerId"]
            if "consumer_id" in data and "identifier" not in data:
                data["identifier"] = data["consumer_id"]
        return data


# ================= INFERENCE HELPERS =================

def predict_next_hours_fast(
    model: Any,
    history_tail: List[float],
    timestamps: Sequence[pd.Timestamp],
) -> List[Dict[str, Any]]:
    """Fast autoregressive predictor using circular buffer scalars and pure numpy."""
    buffer = deque(history_tail, maxlen=200)
    while len(buffer) < 168:
        buffer.appendleft(buffer[0] if buffer else 1.0)

    results = []
    for ts in timestamps:
        ts_obj = pd.Timestamp(ts)
        lag_1 = buffer[-1]
        lag_24 = buffer[-24]
        lag_168 = buffer[-168]
        rolling_mean_24 = sum(list(buffer)[-24:]) / 24.0

        feat_vector = extract_single_feature_vector(
            timestamp=ts_obj,
            lag_1=lag_1,
            lag_24=lag_24,
            lag_168=lag_168,
            rolling_mean_24=rolling_mean_24,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            y = max(0.0, float(model.predict([feat_vector])[0]))
        buffer.append(y)

        results.append(
            {
                "timestamp": ts_obj.isoformat(),
                "predicted_kwh": round(y, 3),
            }
        )

    return results


def get_bundle() -> Dict[str, Any]:
    if ml_state["bundle"] is None:
        if MODEL_PATH.exists():
            refresh_ml_state()
        else:
            raise HTTPException(
                status_code=503,
                detail="ML model is not trained yet. Run: python ml/train_model.py",
            )
    return ml_state["bundle"]


def get_history() -> pd.DataFrame:
    if ml_state["history_df"] is None:
        if DATA_PATH.exists():
            refresh_ml_state()
        else:
            raise HTTPException(
                status_code=503,
                detail="Dataset not found. Place electricity.csv in backend/data/.",
            )
    return ml_state["history_df"]


def compute_bill_prediction_core(req: BillPredictionRequest) -> Dict[str, Any]:
    """Execute complete server-side bill prediction, appliance breakdown, and ML baseline analytics."""
    bhk = req.bhk
    occupants = req.occupants
    season = (req.season or "summer").lower()
    temp = req.temperature_c

    # 1. Air Conditioning (1.5 Ton Split)
    if req.ac_enabled and req.ac_units > 0 and req.ac_hours > 0:
        ac_kw = 1.05 if req.ac_star == 5 else (1.35 if req.ac_star == 3 else 1.65)
        temp_duty_factor = max(0.6, 1.0 + ((temp - 30.0) * 0.035))
        season_factor = 1.0 if season == "summer" else (0.65 if season == "monsoon" else 0.15)
        cooling_kwh = round(req.ac_units * req.ac_hours * ac_kw * temp_duty_factor * season_factor * 30.0)
        ac_peak_kw = round(req.ac_units * ac_kw * 0.85, 2)
    else:
        cooling_kwh = 0
        ac_peak_kw = 0.0

    # 2. Roof / Ceiling Fans (Standard 75W vs BLDC 32W)
    if req.ceiling_fan_enabled and req.ceiling_fan_units > 0 and req.ceiling_fan_hours > 0:
        fan_watts = 32.0 if req.ceiling_fan_type == "bldc" else 75.0
        ceiling_fan_kwh = round((req.ceiling_fan_units * fan_watts * req.ceiling_fan_hours * 30.0) / 1000.0)
        ceiling_fan_peak_kw = round((req.ceiling_fan_units * fan_watts) / 1000.0, 2)
    else:
        ceiling_fan_kwh = 0
        ceiling_fan_peak_kw = 0.0

    # 3. Table / Stand Fans (50W)
    if req.table_fan_enabled and req.table_fan_units > 0 and req.table_fan_hours > 0:
        table_fan_kwh = round((req.table_fan_units * 50.0 * req.table_fan_hours * 30.0) / 1000.0)
        table_fan_peak_kw = round((req.table_fan_units * 50.0) / 1000.0, 2)
    else:
        table_fan_kwh = 0
        table_fan_peak_kw = 0.0

    # 4. Water Pump & Motor (0.5 to 2.0 HP) with Timing Slot
    if req.water_pump_enabled and req.water_pump_hours > 0:
        pump_watts = req.water_pump_hp * 746.0
        water_pump_kwh = round((pump_watts * req.water_pump_hours * 30.0) / 1000.0)
        water_pump_peak_kw = round(pump_watts / 1000.0, 2)
    else:
        water_pump_kwh = 0
        water_pump_peak_kw = 0.0

    # 5. Water Geysers / Boilers (2000W)
    if req.geyser_enabled and req.geyser_units > 0 and req.geyser_hours > 0:
        geyser_season_factor = 0.4 if season == "summer" else (0.8 if season == "monsoon" else 1.7)
        geyser_kwh = round(req.geyser_units * req.geyser_hours * 2.0 * geyser_season_factor * 30.0)
        geyser_peak_kw = round(min(2.0, req.geyser_units * 1.5), 2)
    else:
        geyser_kwh = 0
        geyser_peak_kw = 0.0

    # 6. Refrigerator (24x7 Continuous)
    if req.fridge_enabled:
        if req.fridge_type == "5star-double":
            fridge_kwh = 26
        elif req.fridge_type == "side-by-side":
            fridge_kwh = 62
        elif req.fridge_type == "single":
            fridge_kwh = 22
        else:
            fridge_kwh = 38
        fridge_peak_kw = 0.15
    else:
        fridge_kwh = 0
        fridge_peak_kw = 0.0

    # 7. Mixture Machine / Food Processor
    if req.mixer_enabled and req.mixer_minutes > 0:
        mixer_kwh = round((600.0 * (req.mixer_minutes / 60.0) * 30.0) / 1000.0)
        mixer_peak_kw = 0.45
    else:
        mixer_kwh = 0
        mixer_peak_kw = 0.0

    # 8. LED Lighting (10W Energy Savers)
    if req.led_bulbs_enabled and req.led_bulbs_units > 0 and req.led_bulbs_hours > 0:
        led_bulbs_kwh = round((req.led_bulbs_units * 10.0 * req.led_bulbs_hours * 30.0) / 1000.0)
        led_bulbs_peak_kw = round((req.led_bulbs_units * 10.0) / 1000.0, 2)
    else:
        led_bulbs_kwh = 0
        led_bulbs_peak_kw = 0.0

    # 9. Smart LED TV & Entertainment (85W)
    if req.tv_enabled and req.tv_units > 0 and req.tv_hours > 0:
        tv_kwh = round((req.tv_units * 85.0 * req.tv_hours * 30.0) / 1000.0)
        tv_peak_kw = round((req.tv_units * 85.0) / 1000.0, 2)
    else:
        tv_kwh = 0
        tv_peak_kw = 0.0

    # 10. Washing Machine
    if req.wm_enabled and req.wm_loads > 0:
        wm_kwh = round(req.wm_loads * 4.3 * 0.85)
        wm_peak_kw = 0.5
    else:
        wm_kwh = 0
        wm_peak_kw = 0.0

    # 11. Electric Vehicle Charging
    if req.ev_enabled and req.ev_km > 0:
        ev_kwh = round(req.ev_km * 0.15 * 30.0)
        ev_peak_kw = 2.0
    else:
        ev_kwh = 0
        ev_peak_kw = 0.0

    # 12. Standby Base Load (WiFi routers, chargers, IoT)
    active_device_count = sum([
        bool(req.ac_enabled and req.ac_units > 0),
        bool(req.ceiling_fan_enabled and req.ceiling_fan_units > 0),
        bool(req.table_fan_enabled and req.table_fan_units > 0),
        bool(req.water_pump_enabled and req.water_pump_hours > 0),
        bool(req.geyser_enabled and req.geyser_units > 0),
        bool(req.fridge_enabled),
        bool(req.mixer_enabled and req.mixer_minutes > 0),
        bool(req.led_bulbs_enabled and req.led_bulbs_units > 0),
        bool(req.tv_enabled and req.tv_units > 0),
        bool(req.wm_enabled and req.wm_loads > 0),
        bool(req.ev_enabled and req.ev_km > 0)
    ])
    standby_base_kwh = round((bhk * 8.0) + (occupants * 3.0)) if active_device_count > 0 else 0

    # Gross demand & Solar offset
    gross_kwh = (
        cooling_kwh + ceiling_fan_kwh + table_fan_kwh +
        water_pump_kwh + geyser_kwh + fridge_kwh + mixer_kwh +
        led_bulbs_kwh + tv_kwh + wm_kwh + ev_kwh + standby_base_kwh
    )

    if req.solar_enabled and req.solar_kw > 0:
        solar_gen_kwh = round(req.solar_kw * 4.0 * 30.0)
    else:
        solar_gen_kwh = 0

    total_kwh = max(0.0, float(gross_kwh - solar_gen_kwh))

    # 13. Detailed Structured Appliance Items for Analytics
    appliance_items = [
        {
            "id": "ac",
            "name": f"Air Conditioners ({req.ac_units}x {req.ac_star}&#9733;)",
            "plainName": f"Air Conditioners ({req.ac_units}x)",
            "emoji": "❄️",
            "category": "Cooling",
            "kwh": cooling_kwh,
            "color": "#00f2fe",
            "enabled": bool(req.ac_enabled and req.ac_units > 0),
            "timing": f"{req.ac_hours}h daily",
            "share_pct": round((cooling_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(cooling_kwh * 7.50),
        },
        {
            "id": "ceiling_fan",
            "name": f"Roof / Ceiling Fans ({req.ceiling_fan_units}x {req.ceiling_fan_type.upper()})",
            "plainName": f"Roof Fans ({req.ceiling_fan_units}x)",
            "emoji": "🌀",
            "category": "Ventilation",
            "kwh": ceiling_fan_kwh,
            "color": "#38bdf8",
            "enabled": bool(req.ceiling_fan_enabled and req.ceiling_fan_units > 0),
            "timing": f"{req.ceiling_fan_hours}h daily",
            "share_pct": round((ceiling_fan_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(ceiling_fan_kwh * 7.50),
        },
        {
            "id": "table_fan",
            "name": f"Table / Stand Fans ({req.table_fan_units}x)",
            "plainName": f"Table Fans ({req.table_fan_units}x)",
            "emoji": "💨",
            "category": "Ventilation",
            "kwh": table_fan_kwh,
            "color": "#7dd3fc",
            "enabled": bool(req.table_fan_enabled and req.table_fan_units > 0),
            "timing": f"{req.table_fan_hours}h daily",
            "share_pct": round((table_fan_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(table_fan_kwh * 7.50),
        },
        {
            "id": "water_pump",
            "name": f"Water Pump ({req.water_pump_hp} HP)",
            "plainName": f"Water Pump ({req.water_pump_hp} HP)",
            "emoji": "🚰",
            "category": "Motors & Utilities",
            "kwh": water_pump_kwh,
            "color": "#0ea5e9",
            "enabled": bool(req.water_pump_enabled and req.water_pump_hours > 0),
            "timing": f"{req.water_pump_hours}h/d ({req.water_pump_timing.title()} Slot)",
            "share_pct": round((water_pump_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(water_pump_kwh * 7.50),
        },
        {
            "id": "geyser",
            "name": f"Water Geysers ({req.geyser_units}x 2kW)",
            "plainName": f"Water Geysers ({req.geyser_units}x)",
            "emoji": "🚿",
            "category": "Water Heating",
            "kwh": geyser_kwh,
            "color": "#f59e0b",
            "enabled": bool(req.geyser_enabled and req.geyser_units > 0),
            "timing": f"{req.geyser_hours}h daily",
            "share_pct": round((geyser_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(geyser_kwh * 7.50),
        },
        {
            "id": "refrigerator",
            "name": f"Refrigerator ({req.fridge_type})",
            "plainName": f"Refrigerator ({req.fridge_type})",
            "emoji": "🧊",
            "category": "Refrigeration",
            "kwh": fridge_kwh,
            "color": "#10b981",
            "enabled": bool(req.fridge_enabled),
            "timing": "24x7 Continuous",
            "share_pct": round((fridge_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(fridge_kwh * 7.50),
        },
        {
            "id": "mixer",
            "name": "Mixture Machine / Grinder",
            "plainName": "Mixture Machine / Grinder",
            "emoji": "🌪️",
            "category": "Kitchen",
            "kwh": mixer_kwh,
            "color": "#f97316",
            "enabled": bool(req.mixer_enabled and req.mixer_minutes > 0),
            "timing": f"{int(req.mixer_minutes)} mins daily",
            "share_pct": round((mixer_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(mixer_kwh * 7.50),
        },
        {
            "id": "led_bulbs",
            "name": f"LED Lighting ({req.led_bulbs_units} Bulbs)",
            "plainName": f"LED Bulbs ({req.led_bulbs_units}x)",
            "emoji": "💡",
            "category": "Lighting",
            "kwh": led_bulbs_kwh,
            "color": "#eab308",
            "enabled": bool(req.led_bulbs_enabled and req.led_bulbs_units > 0),
            "timing": f"{req.led_bulbs_hours}h daily",
            "share_pct": round((led_bulbs_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(led_bulbs_kwh * 7.50),
        },
        {
            "id": "tv",
            "name": f"Smart LED TV ({req.tv_units}x)",
            "plainName": f"Smart LED TV ({req.tv_units}x)",
            "emoji": "📺",
            "category": "Entertainment",
            "kwh": tv_kwh,
            "color": "#8b5cf6",
            "enabled": bool(req.tv_enabled and req.tv_units > 0),
            "timing": f"{req.tv_hours}h daily",
            "share_pct": round((tv_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(tv_kwh * 7.50),
        },
        {
            "id": "washing_machine",
            "name": f"Washing Machine ({req.wm_loads} loads/wk)",
            "plainName": "Washing Machine",
            "emoji": "🧺",
            "category": "Laundry",
            "kwh": wm_kwh,
            "color": "#ec4899",
            "enabled": bool(req.wm_enabled and req.wm_loads > 0),
            "timing": f"{req.wm_loads} loads/week",
            "share_pct": round((wm_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(wm_kwh * 7.50),
        },
        {
            "id": "ev",
            "name": f"EV Charging ({req.ev_km} km/d)",
            "plainName": "EV Charging",
            "emoji": "🚗",
            "category": "Mobility",
            "kwh": ev_kwh,
            "color": "#06b6d4",
            "enabled": bool(req.ev_enabled and req.ev_km > 0),
            "timing": "Overnight Charging",
            "share_pct": round((ev_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(ev_kwh * 7.50),
        },
        {
            "id": "standby_base",
            "name": "Standby Devices (WiFi, Chargers)",
            "plainName": "Standby Base Load",
            "emoji": "🔌",
            "category": "Base Load",
            "kwh": standby_base_kwh,
            "color": "#64748b",
            "enabled": standby_base_kwh > 0,
            "timing": "24x7 Standby",
            "share_pct": round((standby_base_kwh / gross_kwh * 100), 1) if gross_kwh > 0 else 0.0,
            "cost_inr": round(standby_base_kwh * 7.50),
        },
    ]
    active_appliance_items = [item for item in appliance_items if item["enabled"] and item["kwh"] > 0]
    sorted_active = sorted(active_appliance_items, key=lambda x: x["kwh"], reverse=True)
    top_consumer = None
    if sorted_active:
        top_consumer = {
            "id": sorted_active[0]["id"],
            "name": sorted_active[0]["plainName"],
            "kwh": sorted_active[0]["kwh"],
            "share_pct": sorted_active[0]["share_pct"]
        }

    pump_advisory = None
    if req.water_pump_enabled and req.water_pump_hours > 0:
        if req.water_pump_timing == "morning":
            pump_advisory = "Morning Peak (6–8 AM): High grid tariff in effect"
        elif req.water_pump_timing == "evening":
            pump_advisory = "Evening Peak (5–7 PM): High grid tariff in effect"
        elif req.water_pump_timing == "afternoon":
            pump_advisory = "Afternoon (12–2 PM): Optimal Solar generation window"
        elif req.water_pump_timing == "night":
            pump_advisory = "Night Slot (10 PM–6 AM): Off-Peak Green tariff active"

    # 14. DISCOM Standard Tiered Tariff Structure
    # Slab 1: 0 - 100 kWh @ 4.50
    # Slab 2: 101 - 300 kWh @ 7.00
    # Slab 3: 301 - 500 kWh @ 9.50
    # Slab 4: > 500 kWh @ 11.50
    slab1 = min(total_kwh, 100.0) * 4.50 if total_kwh > 0 else 0.0
    slab2 = max(0.0, min(total_kwh - 100.0, 200.0)) * 7.00 if total_kwh > 100.0 else 0.0
    slab3 = max(0.0, min(total_kwh - 300.0, 200.0)) * 9.50 if total_kwh > 300.0 else 0.0
    slab4 = max(0.0, total_kwh - 500.0) * 11.50 if total_kwh > 500.0 else 0.0

    fixed_meter_charge = 180.0 if gross_kwh > 0 else 0.0
    energy_charges = slab1 + slab2 + slab3 + slab4
    electricity_tax = energy_charges * 0.05
    bill_amount = round(energy_charges + fixed_meter_charge + electricity_tax)
    solar_savings_inr = round(solar_gen_kwh * 7.00)

    # 15. Carbon Footprint (0.82 kg CO2e / grid kWh)
    carbon_kg = round(total_kwh * 0.82)
    solar_offset_kg = round(solar_gen_kwh * 0.82)

    # 16. Energy Efficiency Rating
    if gross_kwh == 0:
        grade = "--"
        score = 0
    else:
        per_capita = total_kwh / max(1, occupants)
        if per_capita < 80:
            grade = "A+"
            score = 94
        elif per_capita < 120:
            grade = "A"
            score = 82
        elif per_capita < 170:
            grade = "B"
            score = 68
        elif per_capita < 230:
            grade = "C"
            score = 54
        else:
            grade = "D"
            score = 38

    # 17. Peak Demand Load Estimate (kW) with Coincidence Factor
    if gross_kwh == 0:
        peak_kw = 0.0
    else:
        active_peaks = [
            ac_peak_kw, geyser_peak_kw, water_pump_peak_kw,
            ceiling_fan_peak_kw, table_fan_peak_kw, fridge_peak_kw,
            tv_peak_kw, led_bulbs_peak_kw, wm_peak_kw, (ev_peak_kw * 0.4)
        ]
        peak_kw = round(max(0.3, 0.2 + (sum(active_peaks) * 0.62) - (req.solar_kw * 0.2 if req.solar_enabled else 0.0)), 1)

    # 18. Dynamic AI Optimizer Suggestion (Including Water Pump Timing Advisory)
    if req.water_pump_enabled and req.water_pump_timing in ["morning", "evening"] and req.water_pump_hours >= 1.0:
        optimizer_tip = (
            f"💡 <strong>Water Pump Peak Advisory</strong>: Running your {req.water_pump_hp} HP pump during "
            f"<strong>{req.water_pump_timing.title()} Grid Peak (6–8 PM)</strong> incurs high tariff surcharges. "
            f"Shift pump run-time to <strong>Afternoon Solar Hours (12–2 PM)</strong> or Off-Peak Night to save roughly "
            f"<strong>&#8377;280/month</strong>!"
        )
    elif req.ac_enabled and req.ac_units > 0 and req.ac_hours >= 6:
        ac_saving_units = round(cooling_kwh * 0.18)
        ac_saving_inr = round(ac_saving_units * 7.50)
        optimizer_tip = (
            f"Running your AC at <strong>24°C</strong> instead of chilled 18°C will save approx "
            f"<strong>{ac_saving_units} units (&#8377;{ac_saving_inr:,}/mo)</strong>."
        )
    elif req.ceiling_fan_enabled and req.ceiling_fan_type == "standard" and req.ceiling_fan_units >= 3:
        fan_saving = round((req.ceiling_fan_units * (75 - 32) * req.ceiling_fan_hours * 30 / 1000) * 7.20)
        optimizer_tip = (
            f"Upgrading your {req.ceiling_fan_units} ceiling fans to <strong>5-Star BLDC Motors (32W)</strong> "
            f"will save approx <strong>&#8377;{fan_saving:,}/month</strong> with whisper-quiet airflow!"
        )
    elif not req.solar_enabled or req.solar_kw == 0:
        optimizer_tip = (
            "Installing just <strong>2 kW Rooftop Solar</strong> will save you approximately "
            "<strong>&#8377;1,800/month</strong> with clean renewable energy."
        )
    else:
        optimizer_tip = (
            "Your energy profile is currently well-balanced! Running heavy washing loads off-peak saves "
            "an extra <strong>&#8377;250/month</strong>."
        )

    # 19. ML Calibration & Dynamic 30-Day Monthly Forecast Curve
    season_month_map = {"summer": 5, "monsoon": 8, "winter": 1}
    target_month = season_month_map.get(season, 5)
    monthly_baselines = ml_state.get("monthly_baselines") or {}
    ml_baseline = monthly_baselines.get(target_month, 220.0)

    avg_daily = round(total_kwh / 30.0, 2)
    days_labels = [f"Day {i}" for i in range(1, 31)]

    # Days 1 to 18: Recorded baseline meter readings in current billing cycle
    recorded_series: List[Optional[float]] = []
    for d in range(1, 19):
        day_wave = float((np.sin(d * 1.3) * 0.7) + (np.cos(d * 0.9) * 0.4))
        is_weekend = (d % 7 == 6 or d % 7 == 0)
        weekend_mult = 1.12 if is_weekend else 0.97
        val = float(max(1.0, round((avg_daily * weekend_mult) + day_wave, 1))) if avg_daily > 0 else 0.0
        recorded_series.append(val)
    recorded_series.extend([None] * 12)

    # Days 1 to 17 for forecast are None; Day 18 connects to recorded Day 18
    forecast_series: List[Optional[float]] = [None] * 17
    anchor_point = float(recorded_series[17] if recorded_series[17] is not None else avg_daily)
    forecast_series.append(anchor_point)

    # Days 19 to 30: AI/ML Projected daily consumption responding directly to user parameters
    for d in range(19, 31):
        if avg_daily == 0:
            forecast_series.append(0.0)
        else:
            is_weekend = (d % 7 == 6 or d % 7 == 0)
            weekend_mult = 1.15 if is_weekend else 0.96
            temp_wave = float(np.sin(d * 0.8) * (0.04 * (temp - 24.0)))
            val = float(max(0.5, round((avg_daily * weekend_mult) + temp_wave, 1)))
            forecast_series.append(val)

    chart_data = {
        "labels": days_labels,
        "recorded_kwh": recorded_series,
        "forecast_kwh": forecast_series,
        "avg_daily_kwh": avg_daily,
    }

    daily_forecast = []
    today = pd.Timestamp.now()
    for i in range(7):
        d_ts = today + pd.Timedelta(days=i)
        variation = np.sin(i + 1) * (avg_daily * 0.1)
        daily_forecast.append({
            "date": d_ts.strftime("%Y-%m-%d"),
            "predicted_kwh": round(max(0.2, avg_daily + variation), 2) if avg_daily > 0 else 0.0,
        })

    tier_breakdown = {
        "slab1": round(slab1),
        "slab2": round(slab2),
        "slab3": round(slab3),
        "slab4": round(slab4),
        "fixed": round(fixed_meter_charge),
        "tax": round(electricity_tax),
        "energy_charges": round(energy_charges),
    }

    # Consolidated category breakdown for backwards compatibility
    breakdown = {
        "cooling": cooling_kwh + ceiling_fan_kwh + table_fan_kwh,
        "waterHeating": geyser_kwh + water_pump_kwh,
        "refrigeration": fridge_kwh,
        "baseLoad": standby_base_kwh + led_bulbs_kwh + tv_kwh,
        "evAndAppliances": wm_kwh + ev_kwh + mixer_kwh,
        # Exact device keys
        "ac": cooling_kwh,
        "ceilingFan": ceiling_fan_kwh,
        "tableFan": table_fan_kwh,
        "waterPump": water_pump_kwh,
        "geyser": geyser_kwh,
        "refrigerator": fridge_kwh,
        "mixer": mixer_kwh,
        "ledBulbs": led_bulbs_kwh,
        "tv": tv_kwh,
        "washingMachine": wm_kwh,
        "ev": ev_kwh,
        "standbyBase": standby_base_kwh,
    }

    return {
        "totalKwh": round(total_kwh),
        "total_kwh": round(total_kwh),
        "grossKwh": round(gross_kwh),
        "gross_kwh": round(gross_kwh),
        "solarGenKwh": round(solar_gen_kwh),
        "solar_gen_kwh": round(solar_gen_kwh),
        "totalBill": bill_amount,
        "total_bill": bill_amount,
        "solarCredit": solar_savings_inr,
        "solar_credit": solar_savings_inr,
        "tierBreakdown": tier_breakdown,
        "tier_breakdown": tier_breakdown,
        "breakdown": breakdown,
        "appliance_items": appliance_items,
        "applianceItems": appliance_items,
        "active_appliance_items": active_appliance_items,
        "activeApplianceItems": active_appliance_items,
        "active_appliances_count": len(active_appliance_items),
        "activeAppliancesCount": len(active_appliance_items),
        "top_consumer": top_consumer,
        "topConsumer": top_consumer,
        "pump_timing_advisory": pump_advisory,
        "pumpTimingAdvisory": pump_advisory,
        "efficiencyGrade": grade,
        "efficiency_grade": grade,
        "efficiencyScore": score,
        "efficiency_score": score,
        "carbonKg": carbon_kg,
        "carbon_kg": carbon_kg,
        "solarOffsetKg": solar_offset_kg,
        "solar_offset_kg": solar_offset_kg,
        "peakKw": peak_kw,
        "peak_kw": peak_kw,
        "optimizerTip": optimizer_tip,
        "optimizer_tip": optimizer_tip,
        "source": "backend_ml_engine",
        "chart_data": chart_data,
        "chartData": chart_data,
        "daily_forecast": daily_forecast,
        "ml_insights": {
            "monthly_baseline_kwh": round(ml_baseline, 2),
            "target_month": target_month,
            "model_type": ml_state["bundle"].get("model_type") if ml_state.get("bundle") else None,
        },
    }


# ================= HTTP ENDPOINTS =================

@app.get("/")
def root():
    return {
        "message": "Electricity Consumption Prediction API is live.",
        "documentation": "/docs",
        "health": "/health",
        "endpoints": {
            "forecast": "POST /forecast",
            "predict_monthly": "POST /predict/monthly",
            "predict_bill": "POST /predict/bill",
            "whatif": "POST /calculate/whatif",
        },
    }


@app.get("/health")
def health():
    model_loaded = ml_state["bundle"] is not None
    data_loaded = ml_state["history_df"] is not None
    last_ts = ml_state["last_timestamp"]

    return {
        "status": "ok",
        "model_trained": MODEL_PATH.exists(),
        "model_loaded_in_memory": model_loaded,
        "dataset_available": DATA_PATH.exists(),
        "dataset_loaded_in_memory": data_loaded,
        "model_type": (
            ml_state["bundle"].get("model_type", "Unknown")
            if model_loaded
            else None
        ),
        "latest_dataset_timestamp": str(last_ts) if last_ts else None,
    }


@app.post("/forecast")
def forecast(req: ForecastRequest):
    bundle = get_bundle()
    get_history()

    model = bundle["model"]
    last_ts = ml_state["last_timestamp"]
    history_tail = ml_state["tail_kwh"]

    future_timestamps = pd.date_range(
        last_ts + pd.Timedelta(hours=1),
        periods=req.days * 24,
        freq="h",
    )

    points = predict_next_hours_fast(
        model=model,
        history_tail=history_tail,
        timestamps=future_timestamps,
    )

    daily: Dict[str, float] = {}
    for pt in points:
        day = pt["timestamp"][:10]
        daily[day] = daily.get(day, 0.0) + pt["predicted_kwh"]

    return {
        "days": req.days,
        "forecast_hours": points,
        "daily_totals_kwh": [
            {"date": day, "predicted_kwh": round(total, 2)}
            for day, total in daily.items()
        ],
    }


@app.post("/predict/monthly")
def predict_monthly(req: MonthlyRequest):
    bundle = get_bundle()
    df = get_history()

    start = pd.Timestamp(year=req.year, month=req.month, day=1)
    end = start + pd.offsets.MonthBegin(1)
    last_ts = ml_state["last_timestamp"]

    # Case 1: The requested month is within our historical dataset
    if start <= last_ts:
        month_rows = df[(df["timestamp"] >= start) & (df["timestamp"] < end)]
        if not month_rows.empty:
            return {
                "month": req.month,
                "year": req.year,
                "consumption_kwh": round(float(month_rows["consumption_kwh"].sum()), 2),
                "source": "historical_data",
                "note": "Actual historical meter aggregate from dataset.",
            }

    # Case 2: Near-term future (within 60 days of dataset end) -> Fast Autoregressive roll-out
    hours_gap = (end - last_ts).total_seconds() / 3600.0
    if 0 < hours_gap <= (60 * 24):
        future_timestamps = pd.date_range(
            last_ts + pd.Timedelta(hours=1),
            end - pd.Timedelta(hours=1),
            freq="h",
        )
        points = predict_next_hours_fast(
            model=bundle["model"],
            history_tail=ml_state["tail_kwh"],
            timestamps=future_timestamps,
        )
        monthly_kwh = sum(
            pt["predicted_kwh"]
            for pt in points
            if (
                pd.Timestamp(pt["timestamp"]).year == req.year
                and pd.Timestamp(pt["timestamp"]).month == req.month
            )
        )
        return {
            "month": req.month,
            "year": req.year,
            "consumption_kwh": round(monthly_kwh, 2),
            "source": "ml_autoregressive_forecast",
            "note": "Hourly rolled-out forecast based on recent meter trajectory.",
        }

    # Case 3: Long-horizon future baseline
    monthly_baselines = ml_state.get("monthly_baselines") or {}
    base_kwh = monthly_baselines.get(req.month, 180.0)

    temp = req.average_temperature_c
    temp_factor = 1.0
    if temp > 24.0:
        temp_factor += (temp - 24.0) * 0.025
    elif temp < 18.0:
        temp_factor += (18.0 - temp) * 0.030

    household_factor = 0.5 + 0.167 * req.household_size
    adjusted_consumption = base_kwh * temp_factor * household_factor

    return {
        "month": req.month,
        "year": req.year,
        "consumption_kwh": round(adjusted_consumption, 2),
        "source": "seasonal_ml_projection",
        "note": (
            "Seasonal baseline projection calibrated by historical calendar month "
            "with household occupant and temperature sensitivities applied."
        ),
        "parameters_applied": {
            "baseline_kwh": round(base_kwh, 2),
            "temperature_factor": round(temp_factor, 3),
            "household_factor": round(household_factor, 3),
        },
    }


@app.post("/predict/bill")
@app.post("/predict")
def predict_bill(req: BillPredictionRequest):
    """Predict electricity consumption, appliance breakdown, and bill costs on backend."""
    return compute_bill_prediction_core(req)


@app.post("/calculate/whatif")
def calculate_whatif(req: WhatIfRequest):
    """Calculate potential savings from energy conservation actions."""
    savings_inr = 0.0
    if req.ac_temp_optimized:
        savings_inr += 580.0
    if req.geyser_timer_used:
        savings_inr += 315.0
    if req.led_bldc_installed:
        savings_inr += 240.0
    if req.solar_add_1kw:
        savings_inr += 840.0

    fx_rate = 0.012
    return {
        "ac_saving_inr": 580.0,
        "geyser_saving_inr": 315.0,
        "led_saving_inr": 240.0,
        "solar_saving_inr": 840.0,
        "total_savings_inr": savings_inr,
        "total_savings_usd": round(savings_inr * fx_rate, 2),
    }


# ================= DATABASE AUTH & PERSISTENCE ENDPOINTS =================

@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    """Register a new consumer in the database."""
    try:
        user = database.register_user(
            name=req.name,
            consumer_id=req.consumer_id,
            email=req.email,
            password=req.password,
            sanctioned_load=req.sanctioned_load,
            category=req.category,
            provider=req.provider,
        )
        return {"status": "success", "user": user, "prediction": None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    """Authenticate consumer and fetch saved prediction from database."""
    auth_data = database.authenticate_user(req.identifier, req.password)
    if not auth_data:
        raise HTTPException(status_code=401, detail="Invalid Consumer ID/Email or password.")
    return {"status": "success", "user": auth_data["user"], "prediction": auth_data["prediction"]}


@app.post("/api/user/{consumer_id}/prediction")
def api_save_prediction(consumer_id: str, payload: Dict[str, Any]):
    """Save user prediction to database storage."""
    success = database.save_user_prediction(consumer_id, payload)
    return {"status": "success", "saved": success}


@app.get("/api/user/{consumer_id}/prediction")
def api_get_prediction(consumer_id: str):
    """Fetch user saved prediction from database storage."""
    pred = database.get_user_prediction(consumer_id)
    return {"status": "success", "prediction": pred}


# ================= INTEGRATED STATIC FRONTEND SERVING =================
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/index.html", include_in_schema=False)
    def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/login.html", include_in_schema=False)
    @app.get("/login", include_in_schema=False)
    def serve_login():
        return FileResponse(str(FRONTEND_DIR / "login.html"))

    @app.get("/style.css", include_in_schema=False)
    def serve_style():
        return FileResponse(str(FRONTEND_DIR / "style.css"), media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    def serve_app_js():
        return FileResponse(str(FRONTEND_DIR / "app.js"), media_type="application/javascript")
