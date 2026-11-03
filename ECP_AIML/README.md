# VoltVision AI — Electricity Consumption Prediction & Analytics

A full-stack, machine-learning-powered electricity consumption forecasting and utility bill optimization platform.

---

## ⚡ What Changed (Frontend & Backend Integration)

1. **Formula-Based Calculations Removed from Frontend**:
   - Previously, `frontend/app.js` computed monthly energy demand, cooling duty cycles, geyser loads, tariff slab breakdown, and bill amounts via hardcoded JavaScript formulas directly inside the browser.
   - All formula and simulation logic has now been **migrated to the FastAPI Python backend**. The frontend gathers user inputs, debounces changes, queries the backend API (`/predict/bill`), and displays the ML-calibrated results.

2. **Merged Unified Application Server**:
   - The FastAPI backend now natively mounts and serves the frontend (`index.html`, `login.html`, `style.css`, `app.js`).
   - Starting the server runs the complete web app at `http://127.0.0.1:8000/`.
   - Full CORS support is retained so running the frontend via VS Code Live Server (port 5500/5501) or other local ports continues to work without friction.

3. **ML Model Integration**:
   - Trained on historical hourly smart meter consumption (`backend/data/electricity.csv`).
   - Feature engineering pipeline using cyclical temporal encodings (`hour_sin`, `hour_cos`, `month_sin`, `month_cos`), calendar features, lag values (lag-1, lag-24, lag-168), and rolling 24h window means.
   - Autoregressive fast-rollout inference and seasonal monthly baseline projections.

4. **New API Endpoints**:
   - `POST /predict/bill` (or `POST /predict`): End-to-end bill prediction, tiered DISCOM tariff slabs, appliance-level breakdown, carbon footprint, and energy efficiency analytics.
   - `POST /calculate/whatif`: Data-backed financial impact for energy efficiency scenarios (AC set-temperature optimization, smart geyser timers, BLDC fan conversions, and rooftop solar expansions).

---

## 🚀 Quick Start (Running the Merged App)

### 1. Prerequisites & Virtual Environment
From PowerShell in the project root:
```powershell
# Activate existing virtual environment
.\.venv\Scripts\Activate.ps1

# Or create one if starting fresh:
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

### 2. Start the Unified Server (1-Command Runner)
```powershell
python run.py
```
Or directly via `uvicorn`:
```powershell
cd backend
python -m uvicorn main:app --reload --port 8000
```

### 3. Open in Browser
- **Main Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Dedicated Login Portal**: [http://127.0.0.1:8000/login.html](http://127.0.0.1:8000/login.html)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves dashboard web application (or JSON API status) |
| `GET` | `/health` | Healthcheck and model/dataset memory cache status |
| `POST` | `/predict/bill` | Predicts monthly consumption, appliance breakdown & DISCOM bill |
| `POST` | `/forecast` | Autoregressive hourly predictions for next N days |
| `POST` | `/predict/monthly` | Historical / ML projected monthly consumption |
| `POST` | `/calculate/whatif` | Calculates cumulative savings for conservation scenarios |
| `GET` | `/docs` | Interactive OpenAPI / Swagger UI |

---

## 🧪 Testing

Run the automated test suite covering all API endpoints, ML features, and static file serving:
```powershell
$env:PYTHONPATH="backend"; .\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_*.py"
```
