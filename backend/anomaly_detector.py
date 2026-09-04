"""Isolation Forest wrapper used as a second opinion beside weather rules."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

try:  # Supports both `uvicorn main:app` and `uvicorn backend.main:app`.
    from .data_processor import FEATURE_COLUMNS
except ImportError:  # pragma: no cover - used when launched from backend/
    from data_processor import FEATURE_COLUMNS


class IsolationForestDetector:
    def __init__(self, contamination: float = 0.05) -> None:
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=160,
            random_state=73,
        )
        self.is_fitted = False

    def fit(self, features: pd.DataFrame) -> None:
        self.model.fit(self.scaler.fit_transform(features[FEATURE_COLUMNS]))
        self.is_fitted = True

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        if not self.is_fitted:
            raise RuntimeError("The anomaly model has not been fitted.")
        scaled = self.scaler.transform(features[FEATURE_COLUMNS])
        predictions = self.model.predict(scaled)
        # Larger positive values mean more unusual. Rounded scores are easier to demo.
        anomaly_scores = -self.model.decision_function(scaled)
        return pd.DataFrame(
            {
                "ml_anomaly": predictions == -1,
                "ml_score": anomaly_scores.round(4),
            },
            index=features.index,
        )


