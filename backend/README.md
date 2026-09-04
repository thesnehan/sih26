# PS73 Weather Anomaly Detection Backend

Minimal FastAPI backend for the SIH 2026 PS73 dashboard. It generates repeatable synthetic Automatic Weather Station (AWS) data for ten stations and layers explainable domain rules on top of an Isolation Forest model.

## Run it

From the repository root:

```powershell
py -m pip install -r backend/requirements.txt
py -m uvicorn backend.main:app --reload
```

Python 3.11–3.13 is the most reliable choice for this lightweight MVP. If pip tries to build pandas from source (a Meson/Visual Studio error), use a Python 3.13 interpreter instead of installing C++ build tools.

Or, from `backend/`, run `py -m uvicorn main:app --reload`.

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the interactive API. On first start, `data/weather.csv` is generated with 720 deterministic readings and injected faults.

## Frontend endpoints

| Endpoint | Use |
| --- | --- |
| `GET /stations` | station cards, positions, latest reading and alert count |
| `GET /weather?station_id=AWS-01&limit=100` | chart/table readings; add `latest_only=true` for one per station |
| `GET /anomalies?severity=High` | alert feed; filters are optional |
| `GET /station/AWS-01` | station detail page with recent readings and alerts |
| `POST /predict` | check a reading without changing the feed |
| `POST /simulate/step?station_id=AWS-01` | append one simulated reading for a demo |
| `POST /simulate/start?interval_seconds=5` | start a live in-memory feed; stop with `POST /simulate/stop` |

Each weather or anomaly record is deliberately frontend-friendly: flat weather fields plus `is_anomaly`, `severity`, `anomaly_types`, `findings`, `ml_score`, and a concise `explanation`.

## Detection approach

- **Isolation Forest:** finds uncommon multi-variable weather patterns.
- **Rules:** identify missing fields, impossible physical values, sudden changes, stuck sensors, and cross-field/time inconsistencies.
- **Severity:** returns `Normal`, `Low`, `Medium`, `High`, or `Critical`; rule violations take priority over a model-only flag.

This MVP uses no database, authentication, cloud service, or external weather API. Live simulator readings last only until the server restarts; the generated base CSV remains available for repeatable demos.

