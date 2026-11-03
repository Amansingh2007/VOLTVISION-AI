"""SQLite database storage for VoltVision AI users and prediction history."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "voltvision.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create database tables if they do not exist and seed initial demo data."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                consumer_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                sanctioned_load REAL DEFAULT 5.0,
                category TEXT DEFAULT 'Domestic Consumer',
                provider TEXT DEFAULT 'National Smart Grid Connected',
                connection_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Predictions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                consumer_id TEXT UNIQUE NOT NULL,
                bhk INTEGER,
                occupants INTEGER,
                season TEXT,
                temperature_c REAL,
                ac_units INTEGER,
                ac_hours REAL,
                ac_star INTEGER,
                geyser_units INTEGER,
                geyser_hours REAL,
                fridge_type TEXT,
                wm_loads INTEGER,
                solar_kw REAL,
                ev_km REAL,
                total_kwh REAL,
                gross_kwh REAL,
                solar_gen_kwh REAL,
                total_bill REAL,
                solar_credit REAL,
                efficiency_grade TEXT,
                efficiency_score INTEGER,
                carbon_kg INTEGER,
                peak_kw REAL,
                breakdown_json TEXT,
                tier_breakdown_json TEXT,
                chart_data_json TEXT,
                optimizer_tip TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (consumer_id) REFERENCES users (consumer_id)
            )
            """
        )

        # Seed standard demo account if not exists
        cursor.execute("SELECT id FROM users WHERE consumer_id = 'CA-984210'")
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO users (consumer_id, name, email, password, sanctioned_load, category, provider, connection_date)
                VALUES ('CA-984210', 'Aman Sharma', 'aman.sharma@example.com', 'password123', 5.0, 'Domestic Consumer', 'BSES Rajdhani Power Ltd (BRPL)', '2023-01-15')
                """
            )

        conn.commit()


def register_user(
    name: str,
    consumer_id: str,
    email: str,
    password: str,
    sanctioned_load: float = 5.0,
    category: str = "Domestic Consumer",
    provider: str = "National Smart Grid Connected",
) -> Dict[str, Any]:
    """Register a brand new user in the database."""
    cid = consumer_id.strip().upper()
    with get_connection() as conn:
        cursor = conn.cursor()
        # Check duplicate
        cursor.execute("SELECT consumer_id FROM users WHERE consumer_id = ? OR email = ?", (cid, email.strip().lower()))
        existing = cursor.fetchone()
        if existing:
            raise ValueError(f"User with Consumer ID '{cid}' or Email '{email}' already exists.")

        cursor.execute(
            """
            INSERT INTO users (consumer_id, name, email, password, sanctioned_load, category, provider, connection_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, date('now'))
            """,
            (cid, name.strip(), email.strip().lower(), password, sanctioned_load, category, provider),
        )
        conn.commit()

        # Newly registered user has NO saved predictions yet
        return {
            "consumerId": cid,
            "name": name.strip(),
            "email": email.strip().lower(),
            "sanctionedLoad": sanctioned_load,
            "category": category,
            "provider": provider,
            "hasPrediction": False,
            "isNewUser": True,
        }


def authenticate_user(identifier: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user by Consumer ID or Email."""
    ident = identifier.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM users
            WHERE (UPPER(consumer_id) = UPPER(?) OR LOWER(email) = LOWER(?)) AND password = ?
            """,
            (ident, ident, password),
        )
        user_row = cursor.fetchone()
        if not user_row:
            return None

        cid = user_row["consumer_id"]
        # Fetch saved prediction if exists
        prediction = get_user_prediction(cid)
        has_prediction = prediction is not None

        return {
            "user": {
                "consumerId": user_row["consumer_id"],
                "name": user_row["name"],
                "email": user_row["email"],
                "sanctionedLoad": user_row["sanctioned_load"],
                "category": user_row["category"],
                "provider": user_row["provider"],
                "connectionDate": user_row["connection_date"],
                "hasPrediction": has_prediction,
                "isNewUser": not has_prediction,
            },
            "prediction": prediction,
        }


def save_user_prediction(consumer_id: str, pred: Dict[str, Any]) -> bool:
    """Save or update user prediction in SQLite database."""
    cid = consumer_id.strip().upper()
    with get_connection() as conn:
        cursor = conn.cursor()

        # Check if user exists in users table; if not, create minimal profile
        cursor.execute("SELECT id FROM users WHERE consumer_id = ?", (cid,))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO users (consumer_id, name, email, password, sanctioned_load)
                VALUES (?, ?, ?, 'password123', 5.0)
                """,
                (cid, f"User {cid}", f"{cid.lower()}@voltvision.local"),
            )

        breakdown_json = json.dumps(pred.get("breakdown") or {})
        tier_breakdown_json = json.dumps(pred.get("tierBreakdown") or pred.get("tier_breakdown") or {})
        chart_data_json = json.dumps(pred.get("chartData") or pred.get("chart_data") or {})

        cursor.execute(
            """
            INSERT INTO user_predictions (
                consumer_id, bhk, occupants, season, temperature_c,
                ac_units, ac_hours, ac_star, geyser_units, geyser_hours,
                fridge_type, wm_loads, solar_kw, ev_km,
                total_kwh, gross_kwh, solar_gen_kwh, total_bill, solar_credit,
                efficiency_grade, efficiency_score, carbon_kg, peak_kw,
                breakdown_json, tier_breakdown_json, chart_data_json, optimizer_tip,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(consumer_id) DO UPDATE SET
                bhk=excluded.bhk,
                occupants=excluded.occupants,
                season=excluded.season,
                temperature_c=excluded.temperature_c,
                ac_units=excluded.ac_units,
                ac_hours=excluded.ac_hours,
                ac_star=excluded.ac_star,
                geyser_units=excluded.geyser_units,
                geyser_hours=excluded.geyser_hours,
                fridge_type=excluded.fridge_type,
                wm_loads=excluded.wm_loads,
                solar_kw=excluded.solar_kw,
                ev_km=excluded.ev_km,
                total_kwh=excluded.total_kwh,
                gross_kwh=excluded.gross_kwh,
                solar_gen_kwh=excluded.solar_gen_kwh,
                total_bill=excluded.total_bill,
                solar_credit=excluded.solar_credit,
                efficiency_grade=excluded.efficiency_grade,
                efficiency_score=excluded.efficiency_score,
                carbon_kg=excluded.carbon_kg,
                peak_kw=excluded.peak_kw,
                breakdown_json=excluded.breakdown_json,
                tier_breakdown_json=excluded.tier_breakdown_json,
                chart_data_json=excluded.chart_data_json,
                optimizer_tip=excluded.optimizer_tip,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                cid,
                pred.get("bhk", 3),
                pred.get("occupants", 4),
                pred.get("season", "summer"),
                pred.get("temperature_c", pred.get("temp", 36.0)),
                pred.get("ac_units", pred.get("acUnits", 2)),
                pred.get("ac_hours", pred.get("acHours", 8.0)),
                pred.get("ac_star", pred.get("acStar", 5)),
                pred.get("geyser_units", pred.get("geyserUnits", 2)),
                pred.get("geyser_hours", pred.get("geyserHours", 1.5)),
                pred.get("fridge_type", pred.get("fridgeType", "3star-double")),
                pred.get("wm_loads", pred.get("wmLoads", 4)),
                pred.get("solar_kw", pred.get("solarKw", 1.5)),
                pred.get("ev_km", pred.get("evKm", 20.0)),
                pred.get("totalKwh", pred.get("total_kwh", 0)),
                pred.get("grossKwh", pred.get("gross_kwh", 0)),
                pred.get("solarGenKwh", pred.get("solar_gen_kwh", 0)),
                pred.get("totalBill", pred.get("total_bill", 0)),
                pred.get("solarCredit", pred.get("solar_credit", 0)),
                pred.get("efficiencyGrade", pred.get("efficiency_grade", "--")),
                pred.get("efficiencyScore", pred.get("efficiency_score", 0)),
                pred.get("carbonKg", pred.get("carbon_kg", 0)),
                pred.get("peakKw", pred.get("peak_kw", 0.0)),
                breakdown_json,
                tier_breakdown_json,
                chart_data_json,
                pred.get("optimizerTip", pred.get("optimizer_tip", "")),
            ),
        )
        conn.commit()
        return True


def get_user_prediction(consumer_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve saved prediction for a user."""
    cid = consumer_id.strip().upper()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_predictions WHERE consumer_id = ?", (cid,))
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "bhk": row["bhk"],
            "occupants": row["occupants"],
            "season": row["season"],
            "temp": row["temperature_c"],
            "temperature_c": row["temperature_c"],
            "acUnits": row["ac_units"],
            "ac_units": row["ac_units"],
            "acHours": row["ac_hours"],
            "ac_hours": row["ac_hours"],
            "acStar": row["ac_star"],
            "ac_star": row["ac_star"],
            "geyserUnits": row["geyser_units"],
            "geyser_units": row["geyser_units"],
            "geyserHours": row["geyser_hours"],
            "geyser_hours": row["geyser_hours"],
            "fridgeType": row["fridge_type"],
            "fridge_type": row["fridge_type"],
            "wmLoads": row["wm_loads"],
            "wm_loads": row["wm_loads"],
            "solarKw": row["solar_kw"],
            "solar_kw": row["solar_kw"],
            "evKm": row["ev_km"],
            "ev_km": row["ev_km"],
            "totalKwh": row["total_kwh"],
            "total_kwh": row["total_kwh"],
            "grossKwh": row["gross_kwh"],
            "gross_kwh": row["gross_kwh"],
            "solarGenKwh": row["solar_gen_kwh"],
            "solar_gen_kwh": row["solar_gen_kwh"],
            "totalBill": row["total_bill"],
            "total_bill": row["total_bill"],
            "solarCredit": row["solar_credit"],
            "solar_credit": row["solar_credit"],
            "efficiencyGrade": row["efficiency_grade"],
            "efficiency_grade": row["efficiency_grade"],
            "efficiencyScore": row["efficiency_score"],
            "efficiency_score": row["efficiency_score"],
            "carbonKg": row["carbon_kg"],
            "carbon_kg": row["carbon_kg"],
            "peakKw": row["peak_kw"],
            "peak_kw": row["peak_kw"],
            "optimizerTip": row["optimizer_tip"],
            "optimizer_tip": row["optimizer_tip"],
            "breakdown": json.loads(row["breakdown_json"]) if row["breakdown_json"] else {},
            "tierBreakdown": json.loads(row["tier_breakdown_json"]) if row["tier_breakdown_json"] else {},
            "tier_breakdown": json.loads(row["tier_breakdown_json"]) if row["tier_breakdown_json"] else {},
            "chartData": json.loads(row["chart_data_json"]) if row["chart_data_json"] else None,
            "chart_data": json.loads(row["chart_data_json"]) if row["chart_data_json"] else None,
        }
