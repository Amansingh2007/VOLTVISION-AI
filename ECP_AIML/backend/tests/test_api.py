"""Integration and unit tests for FastAPI endpoints."""

import unittest
from pydantic import ValidationError
import main


class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main.refresh_ml_state()

    def test_root_endpoint(self):
        res = main.root()
        self.assertIn("message", res)
        self.assertEqual(res["documentation"], "/docs")

    def test_health_endpoint(self):
        res = main.health()
        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["model_trained"])
        self.assertTrue(res["model_loaded_in_memory"])
        self.assertTrue(res["dataset_available"])
        self.assertTrue(res["dataset_loaded_in_memory"])
        self.assertIsNotNone(res["latest_dataset_timestamp"])

    def test_forecast_valid(self):
        req = main.ForecastRequest(days=2)
        res = main.forecast(req)

        self.assertEqual(res["days"], 2)
        self.assertEqual(len(res["forecast_hours"]), 48)
        self.assertGreaterEqual(len(res["daily_totals_kwh"]), 2)

        for hour in res["forecast_hours"]:
            self.assertIn("timestamp", hour)
            self.assertIn("predicted_kwh", hour)
            self.assertGreaterEqual(hour["predicted_kwh"], 0.0)

    def test_forecast_invalid_days(self):
        with self.assertRaises(ValidationError):
            main.ForecastRequest(days=0)

        with self.assertRaises(ValidationError):
            main.ForecastRequest(days=32)

    def test_predict_monthly_historical(self):
        # 2010-05 is within the dataset
        req = main.MonthlyRequest(year=2010, month=5)
        res = main.predict_monthly(req)

        self.assertEqual(res["year"], 2010)
        self.assertEqual(res["month"], 5)
        self.assertEqual(res["source"], "historical_data")
        self.assertGreater(res["consumption_kwh"], 0.0)

    def test_predict_monthly_future_projection(self):
        # 2026-10 is a future projection
        req = main.MonthlyRequest(
            year=2026,
            month=10,
            household_size=4,
            average_temperature_c=32.0,
        )
        res = main.predict_monthly(req)

        self.assertEqual(res["year"], 2026)
        self.assertEqual(res["month"], 10)
        self.assertEqual(res["source"], "seasonal_ml_projection")
        self.assertGreater(res["consumption_kwh"], 0.0)
        self.assertIn("parameters_applied", res)
        self.assertGreater(res["parameters_applied"]["temperature_factor"], 1.0)
        self.assertGreater(res["parameters_applied"]["household_factor"], 1.0)

    def test_predict_monthly_validation_errors(self):
        with self.assertRaises(ValidationError):
            main.MonthlyRequest(year=1990, month=5)  # Year < 2000

        with self.assertRaises(ValidationError):
            main.MonthlyRequest(year=2024, month=13)  # Month > 12

        with self.assertRaises(ValidationError):
            main.MonthlyRequest(year=2024, month=6, household_size=0)  # Household < 1

    def test_predict_bill_default(self):
        req = main.BillPredictionRequest()
        res = main.predict_bill(req)

        self.assertIn("totalKwh", res)
        self.assertIn("totalBill", res)
        self.assertIn("tierBreakdown", res)
        self.assertIn("breakdown", res)
        self.assertIn("efficiencyGrade", res)
        self.assertIn("carbonKg", res)
        self.assertIn("peakKw", res)
        self.assertIn("optimizerTip", res)
        self.assertEqual(res["source"], "backend_ml_engine")
        self.assertGreater(res["totalBill"], 0)
        self.assertGreater(res["totalKwh"], 0)
        self.assertEqual(len(res["daily_forecast"]), 7)

    def test_predict_bill_camel_case_aliases(self):
        # Validate that camelCase dictionary payload works seamlessly
        payload = {
            "bhk": 2,
            "occupants": 3,
            "season": "winter",
            "temp": 18,
            "acUnits": 1,
            "acHours": 4,
            "acStar": 3,
            "geyserUnits": 1,
            "geyserHours": 1.0,
            "fridgeType": "5star-double",
            "wmLoads": 2,
            "solarKw": 2.0,
            "evKm": 10,
        }
        req = main.BillPredictionRequest.model_validate(payload)
        res = main.predict_bill(req)

        self.assertEqual(req.bhk, 2)
        self.assertEqual(req.occupants, 3)
        self.assertEqual(req.temperature_c, 18.0)
        self.assertEqual(req.ac_units, 1)
        self.assertEqual(req.ac_hours, 4.0)
        self.assertEqual(req.ac_star, 3)
        self.assertEqual(req.solar_kw, 2.0)
        self.assertGreater(res["solarGenKwh"], 0)
        self.assertIn(res["efficiencyGrade"], ["A+", "A", "B", "C", "D"])

    def test_calculate_whatif(self):
        req = main.WhatIfRequest(
            ac_temp_optimized=True,
            geyser_timer_used=True,
            led_bldc_installed=True,
            solar_add_1kw=True,
        )
        res = main.calculate_whatif(req)

        self.assertEqual(res["ac_saving_inr"], 580.0)
        self.assertEqual(res["geyser_saving_inr"], 315.0)
        self.assertEqual(res["led_saving_inr"], 240.0)
        self.assertEqual(res["solar_saving_inr"], 840.0)
        self.assertEqual(res["total_savings_inr"], 580.0 + 315.0 + 240.0 + 840.0)
        self.assertGreater(res["total_savings_usd"], 0)

    def test_static_routes_exist(self):
        self.assertTrue(main.FRONTEND_DIR.exists())
        self.assertTrue((main.FRONTEND_DIR / "index.html").exists())
        self.assertTrue((main.FRONTEND_DIR / "app.js").exists())
        self.assertTrue((main.FRONTEND_DIR / "style.css").exists())

    def test_auth_and_prediction_persistence(self):
        import uuid
        test_id = f"CA-TEST-{uuid.uuid4().hex[:6].upper()}"
        reg_req = main.RegisterRequest(
            name="Test User",
            consumer_id=test_id,
            email=f"{test_id.lower()}@example.com",
            password="securepassword123",
            sanctioned_load=5.0,
            category="Domestic Consumer",
            provider="Test Grid"
        )
        reg_res = main.api_register(reg_req)
        self.assertEqual(reg_res["status"], "success")
        self.assertEqual(reg_res["user"]["consumerId"], test_id)

        # Login with registered user
        login_req = main.LoginRequest(
            identifier=test_id,
            password="securepassword123"
        )
        login_res = main.api_login(login_req)
        self.assertEqual(login_res["status"], "success")
        self.assertEqual(login_res["user"]["consumerId"], test_id)
        # New user has no predictions yet
        self.assertIsNone(login_res["prediction"])

        # Save prediction
        sample_pred = {
            "bhk": 3,
            "occupants": 4,
            "season": "summer",
            "temperature_c": 35.0,
            "ac_units": 2,
            "ac_hours": 8.0,
            "ac_star": 5,
            "geyser_units": 1,
            "geyser_hours": 1.0,
            "fridge_type": "3star-double",
            "wm_loads": 3,
            "solar_kw": 2.0,
            "ev_km": 15.0,
            "total_kwh": 380,
            "gross_kwh": 500,
            "solar_gen_kwh": 120,
            "total_bill": 2850,
            "solar_credit": 960,
            "efficiency_grade": "A",
            "efficiency_score": 85,
            "carbon_kg": 310,
            "peak_kw": 2.6,
            "breakdown": {"cooling": 180, "waterHeating": 50, "refrigeration": 40, "baseLoad": 60, "evAndAppliances": 50},
            "tier_breakdown": {"slab1": 500, "slab2": 1000, "slab3": 1350, "fixed": 250},
            "chart_data": {"labels": ["Day 1"], "avg_daily_kwh": 12.6},
            "optimizer_tip": "Keep AC at 24C"
        }
        save_res = main.api_save_prediction(test_id, sample_pred)
        self.assertEqual(save_res["status"], "success")

        # Retrieve prediction
        get_res = main.api_get_prediction(test_id)
        self.assertIsNotNone(get_res["prediction"])
        self.assertEqual(get_res["prediction"]["total_kwh"], 380)
        self.assertEqual(get_res["prediction"]["efficiency_grade"], "A")

        # Subsequent login should now include the saved prediction
        login_res_2 = main.api_login(login_req)
        self.assertIsNotNone(login_res_2["prediction"])
        self.assertEqual(login_res_2["prediction"]["total_kwh"], 380)


if __name__ == "__main__":
    unittest.main()
