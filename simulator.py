"""Small in-memory live weather feed for dashboard demos."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import random
from typing import Any


class WeatherSimulator:
    def __init__(self, seed: int = 2026) -> None:
        self.random = random.Random(seed)

    def next_reading(self, station_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        sunlight = max(0.0, math.sin(math.pi * (now.hour - 5) / 14))
        reading: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "station_id": station_id,
            "temperature": round(25 + 5 * sunlight + self.random.gauss(0, 0.8), 2),
            "humidity": round(75 - 20 * sunlight + self.random.gauss(0, 3), 2),
            "pressure": round(1012 + self.random.gauss(0, 1.4), 2),
            "wind_speed": round(max(0, 4 + 5 * sunlight + self.random.gauss(0, 1.5)), 2),
            "rainfall": round(max(0, self.random.gammavariate(0.35, 0.8) - 0.25), 2),
            "solar_radiation": round(max(0, 850 * sunlight + self.random.gauss(0, 25)), 2),
        }
        # Roughly one visible fault every 20 simulator steps, useful during a live demo.
        if self.random.random() < 0.05:
            fault = self.random.choice(["humidity", "temperature", "wind_speed"])
            reading[fault] = {"humidity": 125.0, "temperature": 48.0, "wind_speed": -2.0}[fault]
        return reading


