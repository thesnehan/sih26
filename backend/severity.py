"""Severity selection and short operator-friendly anomaly explanations."""

from __future__ import annotations

from typing import Iterable

try:  # Supports both package and script-style launches.
    from .rule_engine import RuleFinding
except ImportError:  # pragma: no cover
    from rule_engine import RuleFinding


class SeverityClassifier:
    RANK = {"Normal": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}

    def classify(self, findings: Iterable[RuleFinding], ml_anomaly: bool) -> str:
        findings = list(findings)
        if not findings:
            return "Low" if ml_anomaly else "Normal"
        highest = max(findings, key=lambda finding: self.RANK[finding.severity]).severity
        high_count = sum(finding.severity == "High" for finding in findings)
        if highest == "Critical" or high_count >= 2:
            return "Critical"
        return highest


def explain_anomaly(
    findings: Iterable[RuleFinding], ml_anomaly: bool, severity: str
) -> str:
    findings = list(findings)
    if not findings and not ml_anomaly:
        return "Reading is within the configured weather-station checks."

    reasons = [finding.message for finding in findings[:2]]
    if ml_anomaly:
        reasons.append("Isolation Forest also considers this reading unusual compared with recent station data.")
    prefix = f"{severity} alert: "
    return prefix + " ".join(reasons)


