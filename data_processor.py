"""Dataset creation, validation, and model-safe preprocessing."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "temperature",
    "humidity",
    "pressure",
    "wind_speed",
    "rainfall",
    "solar_radiation",
]
REQUIRED_COLUMNS = ["timestamp", "station_id", *FEATURE_COLUMNS]


class WeatherDataProcessor:
    """Creates deterministic demo data and prepares it for anomaly detection.

    Missing values are intentionally retained in the raw data for the rule engine.
    ``prepare_features`` returns a separate imputed copy for Isolation Forest.
    """

    def __init__(self, data_path: str | Path):
        self.data_path = Path(data_path)

    def load_or_create(self) -> pd.DataFrame:
        if self.data_path.exists():
            data = pd.read_csv(self.data_path)
        else:
            data = self.generate_synthetic_data()
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            data.to_csv(self.data_path, index=False)
        return self.validate_and_sort(data)

    @staticmethod
    def validate_and_sort(data: pd.DataFrame) -> pd.DataFrame:
        missing_columns = set(REQUIRED_COLUMNS) - set(data.columns)
        if missing_columns:
            raise ValueError(f"Weather data is missing columns: {sorted(missing_columns)}")

        result = data.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
        if result["timestamp"].isna().any():
            raise ValueError("Every weather record needs a valid timestamp.")
        for column in FEATURE_COLUMNS:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        return result.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    @staticmethod
    def prepare_features(data: pd.DataFrame) -> pd.DataFrame:
        """Impute numeric values without modifying the raw API records."""
        features = data[FEATURE_COLUMNS].copy()
        station_ids = data["station_id"]
        # Station medians preserve local weather patterns better than one global fill.
        for column in FEATURE_COLUMNS:
            features[column] = features[column].fillna(features.groupby(station_ids)[column].transform("median"))
            features[column] = features[column].fillna(features[column].median())
            features[column] = features[column].fillna(0.0)
        return features

    @staticmethod
    def generate_synthetic_data(
        stations: Iterable[str] | None = None, readings_per_station: int = 72
    ) -> pd.DataFrame:
        """Create 10 stations x 72 hourly readings with labelled injected faults."""
        rng = np.random.default_rng(73)
        station_ids = list(stations or [f"AWS-{number:02d}" for number in range(1, 11)])
        timestamps = pd.date_range(
            "2026-08-29T00:00:00Z", periods=readings_per_station, freq="h", tz="UTC"
        )
        rows: list[dict] = []
        for station_index, station_id in enumerate(station_ids):
            station_offset = (station_index - 4.5) * 0.35
            for hour_index, timestamp in enumerate(timestamps):
                hour = timestamp.hour
                daytime = max(0.0, np.sin(np.pi * (hour - 5) / 14))
                rows.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "station_id": station_id,
                        "temperature": round(25 + station_offset + 5 * daytime + rng.normal(0, 0.7), 2),
                        "humidity": round(75 - 20 * daytime + rng.normal(0, 3.0), 2),
                        "pressure": round(1012 + station_offset + rng.normal(0, 1.8), 2),
                        "wind_speed": round(max(0, 4 + 5 * daytime + rng.normal(0, 1.4)), 2),
                        "rainfall": round(max(0, rng.gamma(0.35, 0.8) - 0.25), 2),
                        "solar_radiation": round(max(0, 850 * daytime + rng.normal(0, 24)), 2),
                        "injected_anomaly": "",
                    }
                )
        data = pd.DataFrame(rows)

        # Fixed positions keep the demo repeatable and make every rule observable.
        def row(station: str, hour_index: int) -> int:
            return data.index[(data.station_id == station) & (data.timestamp == timestamps[hour_index].isoformat())][0]

        sudden = row("AWS-01", 24)
        data.loc[sudden, "temperature"] = 47.8
        data.loc[sudden, "injected_anomaly"] = "sudden_temperature_change"

        impossible = row("AWS-02", 32)
        data.loc[impossible, "humidity"] = 132.0
        data.loc[impossible, "injected_anomaly"] = "impossible_humidity"

        missing = row("AWS-03", 40)
        data.loc[missing, "pressure"] = np.nan
        data.loc[missing, "injected_anomaly"] = "missing_pressure"

        # Four identical consecutive readings simulate a stuck temperature sensor.
        stuck_indices = [row("AWS-04", hour_index) for hour_index in range(45, 49)]
        data.loc[stuck_indices, "temperature"] = 28.25
        data.loc[stuck_indices, "injected_anomaly"] = "stuck_temperature_sensor"

        night_solar = row("AWS-05", 3)
        data.loc[night_solar, "solar_radiation"] = 740.0
        data.loc[night_solar, "injected_anomaly"] = "night_solar_inconsistency"

        rain_humidity = row("AWS-06", 52)
        data.loc[rain_humidity, ["rainfall", "humidity"]] = [38.0, 22.0]
        data.loc[rain_humidity, "injected_anomaly"] = "rain_humidity_inconsistency"

        wind = row("AWS-07", 60)
        data.loc[wind, "wind_speed"] = -3.0
        data.loc[wind, "injected_anomaly"] = "impossible_wind_speed"

        return data


