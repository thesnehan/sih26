"""FastAPI application for the PS73 Automatic Weather Station MVP."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

try:  # Enables both documented launch commands.
    from .anomaly_detector import IsolationForestDetector
    from .data_processor import FEATURE_COLUMNS, WeatherDataProcessor
    from .rule_engine import WeatherRuleEngine
    from .severity import SeverityClassifier, explain_anomaly
    from .simulator import WeatherSimulator
except ImportError:  # pragma: no cover - for `cd backend; uvicorn main:app`
    from anomaly_detector import IsolationForestDetector
    from data_processor import FEATURE_COLUMNS, WeatherDataProcessor
    from rule_engine import WeatherRuleEngine
    from severity import SeverityClassifier, explain_anomaly
    from simulator import WeatherSimulator


class WeatherPredictionRequest(BaseModel):
    """One weather reading. Any absent measurement is itself checked as an anomaly."""

    station_id: str = Field(examples=["AWS-01"], min_length=1, max_length=30)
    timestamp: datetime | None = Field(default=None, examples=["2026-09-04T10:00:00Z"])
    temperature: float | None = Field(default=None, examples=[25.4])
    humidity: float | None = Field(default=None, examples=[72.0])
    pressure: float | None = Field(default=None, examples=[1012.0])
    wind_speed: float | None = Field(default=None, examples=[8.2])
    rainfall: float | None = Field(default=None, examples=[0.0])
    solar_radiation: float | None = Field(default=None, examples=[540.0])


class WeatherService:
    """Keeps the MVP state in memory; no database is required for the demo."""

    def __init__(self, data_path: Path) -> None:
        self.processor = WeatherDataProcessor(data_path)
        self.data = self.processor.load_or_create()
        self.detector = IsolationForestDetector()
        self.detector.fit(self.processor.prepare_features(self.data))
        self.rules = WeatherRuleEngine()
        self.severity = SeverityClassifier()
        self.simulator = WeatherSimulator()
        self.records: list[dict[str, Any]] = []
        self._simulator_task: asyncio.Task[None] | None = None
        self._stop_simulator = asyncio.Event()
        self._rebuild_records()

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, np.generic):
            return value.item()
        return value

    def _serialise(
        self,
        raw_record: dict[str, Any],
        ml_anomaly: bool,
        ml_score: float,
        previous: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        findings = self.rules.evaluate(raw_record, previous, history)
        alert = bool(findings) or bool(ml_anomaly)
        severity = self.severity.classify(findings, bool(ml_anomaly))
        response = {
            "station_id": str(raw_record["station_id"]),
            "timestamp": self._json_value(raw_record["timestamp"]),
            **{field: self._json_value(raw_record.get(field)) for field in FEATURE_COLUMNS},
            "is_anomaly": alert,
            "severity": severity,
            "anomaly_types": sorted({finding.code for finding in findings}),
            "findings": [finding.to_dict() for finding in findings],
            "ml_anomaly": bool(ml_anomaly),
            "ml_score": round(float(ml_score), 4),
            "explanation": explain_anomaly(findings, bool(ml_anomaly), severity),
        }
        return response

    def _rebuild_records(self) -> None:
        features = self.processor.prepare_features(self.data)
        ml_results = self.detector.predict(features)
        records: list[dict[str, Any]] = []
        for station_id, station_data in self.data.groupby("station_id", sort=True):
            history: list[dict[str, Any]] = []
            previous: dict[str, Any] | None = None
            for index, row in station_data.iterrows():
                raw = row.to_dict()
                ml = ml_results.loc[index]
                records.append(
                    self._serialise(raw, bool(ml.ml_anomaly), float(ml.ml_score), previous, history)
                )
                history.append(raw)
                history = history[-3:]
                previous = raw
        self.records = sorted(records, key=lambda item: (item["timestamp"], item["station_id"]))

    @staticmethod
    def _normalise_input(payload: WeatherPredictionRequest) -> dict[str, Any]:
        timestamp = payload.timestamp or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return {
            "station_id": payload.station_id.strip().upper(),
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            **{field: getattr(payload, field) for field in FEATURE_COLUMNS},
        }

    def _predict_raw(self, raw: dict[str, Any]) -> dict[str, Any]:
        station_history = self.data[self.data["station_id"] == raw["station_id"]].copy()
        combined = pd.concat([station_history, pd.DataFrame([raw])], ignore_index=True)
        features = self.processor.prepare_features(combined)
        ml = self.detector.predict(features.iloc[[-1]]).iloc[0]
        ordered_history = station_history.sort_values("timestamp")
        recent = [row.to_dict() for _, row in ordered_history.tail(3).iterrows()]
        previous = recent[-1] if recent else None
        return self._serialise(raw, bool(ml.ml_anomaly), float(ml.ml_score), previous, recent)

    def predict(self, payload: WeatherPredictionRequest) -> dict[str, Any]:
        return self._predict_raw(self._normalise_input(payload))

    def ingest(self, payload: WeatherPredictionRequest) -> dict[str, Any]:
        raw = self._normalise_input(payload)
        prediction = self._predict_raw(raw)
        new_row = {**raw, "injected_anomaly": ""}
        self.data = self.processor.validate_and_sort(pd.concat([self.data, pd.DataFrame([new_row])], ignore_index=True))
        self._rebuild_records()
        return prediction

    def station_ids(self) -> list[str]:
        return sorted(self.data["station_id"].unique().tolist())

    def latest_for_station(self, station_id: str) -> dict[str, Any] | None:
        candidates = [item for item in self.records if item["station_id"] == station_id]
        return max(candidates, key=lambda item: item["timestamp"]) if candidates else None

    async def _live_loop(self, interval_seconds: int) -> None:
        index = 0
        try:
            while not self._stop_simulator.is_set():
                station_id = self.station_ids()[index % len(self.station_ids())]
                self.ingest(WeatherPredictionRequest(**self.simulator.next_reading(station_id)))
                index += 1
                try:
                    await asyncio.wait_for(self._stop_simulator.wait(), timeout=interval_seconds)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    def start_simulator(self, interval_seconds: int) -> bool:
        if self._simulator_task and not self._simulator_task.done():
            return False
        self._stop_simulator = asyncio.Event()
        self._simulator_task = asyncio.create_task(self._live_loop(interval_seconds))
        return True

    async def stop_simulator(self) -> bool:
        if not self._simulator_task or self._simulator_task.done():
            return False
        self._stop_simulator.set()
        await self._simulator_task
        return True

    @property
    def simulator_running(self) -> bool:
        return bool(self._simulator_task and not self._simulator_task.done())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.weather = WeatherService(Path(__file__).parent / "data" / "weather.csv")
    yield
    await app.state.weather.stop_simulator()


app = FastAPI(
    title="PS73 Weather Anomaly Detection API",
    description="Demo-ready AI and rule-based anomaly detection for Automatic Weather Stations.",
    version="1.0.0",
    lifespan=lifespan,
)


def weather_service(request: Request) -> WeatherService:
    return request.app.state.weather


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    return {"message": "PS73 Weather Anomaly Detection API", "status": "running", "docs": "/docs"}


@app.get("/health", tags=["System"])
def health(request: Request) -> dict[str, Any]:
    service = weather_service(request)
    return {
        "status": "healthy",
        "stations": len(service.station_ids()),
        "readings_loaded": len(service.records),
        "simulator_running": service.simulator_running,
    }


@app.get("/stations", tags=["Weather"])
def stations(request: Request) -> dict[str, Any]:
    service = weather_service(request)
    items = []
    for position, station_id in enumerate(service.station_ids(), start=1):
        station_records = [item for item in service.records if item["station_id"] == station_id]
        latest = service.latest_for_station(station_id)
        items.append(
            {
                "station_id": station_id,
                "name": f"Automatic Weather Station {position:02d}",
                "location": {"latitude": round(19.0 + position * 0.12, 4), "longitude": round(73.0 + position * 0.11, 4)},
                "latest": latest,
                "anomaly_count": sum(record["is_anomaly"] for record in station_records),
            }
        )
    return {"count": len(items), "stations": items}


@app.get("/weather", tags=["Weather"])
def weather(
    request: Request,
    station_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    latest_only: bool = False,
) -> dict[str, Any]:
    service = weather_service(request)
    target = station_id.strip().upper() if station_id else None
    if target and target not in service.station_ids():
        raise HTTPException(status_code=404, detail=f"Unknown station: {target}")
    records = [item for item in service.records if target is None or item["station_id"] == target]
    if latest_only:
        records = [service.latest_for_station(item) for item in (target and [target] or service.station_ids())]
    records = sorted(records, key=lambda item: item["timestamp"], reverse=True)[:limit]
    return {"count": len(records), "station_id": target, "records": records}


@app.get("/anomalies", tags=["Anomalies"])
def anomalies(
    request: Request,
    station_id: str | None = None,
    severity: str | None = Query(default=None, pattern="^(Low|Medium|High|Critical|Normal)$"),
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, Any]:
    service = weather_service(request)
    target = station_id.strip().upper() if station_id else None
    if target and target not in service.station_ids():
        raise HTTPException(status_code=404, detail=f"Unknown station: {target}")
    records = [
        item
        for item in service.records
        if item["is_anomaly"]
        and (target is None or item["station_id"] == target)
        and (severity is None or item["severity"] == severity)
    ]
    records = sorted(records, key=lambda item: (item["severity"], item["timestamp"]), reverse=True)[:limit]
    return {"count": len(records), "station_id": target, "severity": severity, "anomalies": records}


@app.get("/station/{station_id}", tags=["Weather"])
def station_detail(station_id: str, request: Request) -> dict[str, Any]:
    service = weather_service(request)
    station_id = station_id.strip().upper()
    if station_id not in service.station_ids():
        raise HTTPException(status_code=404, detail=f"Unknown station: {station_id}")
    records = [item for item in service.records if item["station_id"] == station_id]
    anomalies_for_station = [item for item in records if item["is_anomaly"]]
    return {
        "station_id": station_id,
        "latest": service.latest_for_station(station_id),
        "reading_count": len(records),
        "anomaly_count": len(anomalies_for_station),
        "recent_readings": sorted(records, key=lambda item: item["timestamp"], reverse=True)[:24],
        "recent_anomalies": sorted(anomalies_for_station, key=lambda item: item["timestamp"], reverse=True)[:10],
    }


@app.post("/predict", tags=["Anomalies"])
def predict(reading: WeatherPredictionRequest, request: Request) -> dict[str, Any]:
    """Evaluate one incoming reading without adding it to the dashboard feed."""
    return weather_service(request).predict(reading)


@app.post("/simulate/step", tags=["Simulator"])
def simulate_step(request: Request, station_id: str | None = None) -> dict[str, Any]:
    service = weather_service(request)
    target = (station_id or service.station_ids()[0]).strip().upper()
    if target not in service.station_ids():
        raise HTTPException(status_code=404, detail=f"Unknown station: {target}")
    reading = WeatherPredictionRequest(**service.simulator.next_reading(target))
    return service.ingest(reading)


@app.post("/simulate/start", tags=["Simulator"])
async def start_simulator(
    request: Request, interval_seconds: Annotated[int, Query(ge=1, le=60)] = 5
) -> dict[str, Any]:
    started = weather_service(request).start_simulator(interval_seconds)
    return {
        "status": "started" if started else "already_running",
        "interval_seconds": interval_seconds,
    }


@app.post("/simulate/stop", tags=["Simulator"])
async def stop_simulator(request: Request) -> dict[str, str]:
    stopped = await weather_service(request).stop_simulator()
    return {"status": "stopped" if stopped else "not_running"}


@app.get("/simulate/status", tags=["Simulator"])
def simulator_status(request: Request) -> dict[str, Any]:
    service = weather_service(request)
    return {"running": service.simulator_running, "stations": service.station_ids()}


