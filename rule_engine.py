"""Transparent, domain-specific weather-station anomaly rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd

try:  # Supports both package and script-style launches.
    from .data_processor import FEATURE_COLUMNS
except ImportError:  # pragma: no cover
    from data_processor import FEATURE_COLUMNS


@dataclass(frozen=True)
class RuleFinding:
    code: str
    category: str
    severity: str
    message: str
    field: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeatherRuleEngine:
    """Rules intentionally favour explainability over opaque model-only alerts."""

    LIMITS = {
        "temperature": (-40.0, 60.0, "°C"),
        "humidity": (0.0, 100.0, "%"),
        "pressure": (870.0, 1085.0, "hPa"),
        "wind_speed": (0.0, 70.0, "m/s"),
        "rainfall": (0.0, 250.0, "mm/h"),
        "solar_radiation": (0.0, 1400.0, "W/m²"),
    }
    SUDDEN_CHANGE_LIMITS = {
        "temperature": (8.0, "°C in one hour"),
        "humidity": (35.0, "% in one hour"),
        "pressure": (12.0, "hPa in one hour"),
        "wind_speed": (25.0, "m/s in one hour"),
        "rainfall": (40.0, "mm/h in one hour"),
        "solar_radiation": (800.0, "W/m² in one hour"),
    }
    # Rainfall and solar radiation legitimately stay at zero for extended periods.
    # Use channels expected to vary continuously for a meaningful stuck-sensor check.
    STUCK_SENSOR_FIELDS = ("temperature", "humidity", "pressure", "wind_speed")

    @staticmethod
    def _value(record: dict[str, Any], field: str) -> float | None:
        value = record.get(field)
        return None if value is None or pd.isna(value) else float(value)

    def evaluate(
        self,
        record: dict[str, Any],
        previous: dict[str, Any] | None = None,
        recent_records: Iterable[dict[str, Any]] = (),
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []

        for field in FEATURE_COLUMNS:
            value = self._value(record, field)
            if value is None:
                findings.append(
                    RuleFinding(
                        code="missing_value",
                        category="missing_data",
                        severity="High",
                        field=field,
                        message=f"{field.replace('_', ' ').title()} is missing from this reading.",
                    )
                )
                continue
            lower, upper, unit = self.LIMITS[field]
            if not lower <= value <= upper:
                findings.append(
                    RuleFinding(
                        code="impossible_value",
                        category="physical_limit",
                        severity="Critical",
                        field=field,
                        message=(
                            f"{field.replace('_', ' ').title()} is {value:g}{unit}, "
                            f"outside the plausible {lower:g}–{upper:g}{unit} range."
                        ),
                    )
                )

        if previous:
            for field, (limit, unit) in self.SUDDEN_CHANGE_LIMITS.items():
                current = self._value(record, field)
                old = self._value(previous, field)
                if current is not None and old is not None and abs(current - old) > limit:
                    difference = abs(current - old)
                    findings.append(
                        RuleFinding(
                            code="sudden_change",
                            category="rate_of_change",
                            severity="High",
                            field=field,
                            message=(
                                f"{field.replace('_', ' ').title()} changed by {difference:.1f} {unit}; "
                                f"the alert threshold is {limit:g} {unit}."
                            ),
                        )
                    )

        # A sensor returning exactly the same value four times is likely stuck.
        history = [*recent_records, record]
        if len(history) >= 4:
            last_four = history[-4:]
            for field in self.STUCK_SENSOR_FIELDS:
                values = [self._value(item, field) for item in last_four]
                if None not in values and max(values) - min(values) < 0.001:
                    findings.append(
                        RuleFinding(
                            code="stuck_sensor",
                            category="sensor_health",
                            severity="High",
                            field=field,
                            message=(
                                f"{field.replace('_', ' ').title()} has remained at "
                                f"{values[-1]:g} for four consecutive readings."
                            ),
                        )
                    )

        timestamp = pd.to_datetime(record.get("timestamp"), utc=True, errors="coerce")
        solar = self._value(record, "solar_radiation")
        if solar is not None and not pd.isna(timestamp) and (timestamp.hour < 5 or timestamp.hour >= 20) and solar > 80:
            findings.append(
                RuleFinding(
                    code="sensor_inconsistency",
                    category="cross_field",
                    severity="High",
                    field="solar_radiation",
                    message=f"Solar radiation is {solar:g} W/m² during night-time hours.",
                )
            )

        rainfall = self._value(record, "rainfall")
        humidity = self._value(record, "humidity")
        if rainfall is not None and humidity is not None and rainfall >= 15 and humidity < 40:
            findings.append(
                RuleFinding(
                    code="sensor_inconsistency",
                    category="cross_field",
                    severity="Medium",
                    field="rainfall",
                    message=(
                        f"Rainfall is {rainfall:g} mm/h while humidity is only {humidity:g}%, "
                        "which is internally inconsistent."
                    ),
                )
            )
        return findings


