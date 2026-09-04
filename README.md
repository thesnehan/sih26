# SIH26 — PS73 Weather Anomaly Detection

Hackathon MVP for detecting anomalies in Automatic Weather Station readings.

The complete Member 1 FastAPI backend is in [`backend/`](backend/README.md). It provides synthetic weather data, Isolation Forest detection, explainable domain rules, severity classification, frontend-ready APIs, and a live demo simulator.

## Run the backend

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API.
