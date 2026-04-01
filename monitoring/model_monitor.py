"""
model_monitor.py — LSTM model health monitor for CityPulse.

Detects anomaly score distribution issues and per-channel PSI drift.

Usage:
  python monitoring/model_monitor.py            # full health report
  python monitoring/model_monitor.py --city Zurich  # single city
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from database.supabase_client import SupabaseClient

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

CITY_NAMES = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]

CONTRIBUTION_COLS = [
    "temp_contribution", "humidity_contribution", "wind_contribution",
    "precip_contribution", "pm25_contribution", "pm10_contribution",
]

# Thresholds
SCORE_MEAN_HIGH  = 0.8    # model always alerting
SCORE_MEAN_LOW   = 0.01   # model never detecting
SCORE_STD_MIN    = 0.001  # scores not varying (model stuck)
CONTRIB_DOMINANT = 0.80   # one channel > 80% → calibration issue
PSI_WARN         = 0.10   # minor drift
PSI_ALERT        = 0.20   # significant drift → retrain signal


def _compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Computes Population Stability Index between two distributions.

    PSI < 0.1  → no significant change
    PSI 0.1–0.2 → moderate change (warning)
    PSI > 0.2  → significant change (retrain signal)

    Args:
        expected: Reference distribution values (e.g. last 7 days).
        actual:   Current distribution values (e.g. previous 7 days).
        bins:     Number of histogram bins.

    Returns:
        PSI value (float).
    """
    if len(expected) < 5 or len(actual) < 5:
        return 0.0

    breakpoints = np.linspace(
        min(expected.min(), actual.min()),
        max(expected.max(), actual.max()) + 1e-9,
        bins + 1,
    )

    def _bucket_pcts(arr):
        counts, _ = np.histogram(arr, bins=breakpoints)
        pcts = counts / len(arr)
        pcts = np.where(pcts == 0, 1e-4, pcts)
        return pcts

    e_pcts = _bucket_pcts(expected)
    a_pcts = _bucket_pcts(actual)
    return float(np.sum((a_pcts - e_pcts) * np.log(a_pcts / e_pcts)))


class ModelMonitor:
    """Monitors LSTM autoencoder health across all 8 Swiss cities."""

    def __init__(self) -> None:
        self.db = SupabaseClient()

    def _fetch_scores(self, city: str, hours: int) -> pd.DataFrame:
        """Fetches anomaly scores for a city over the last N hours."""
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            resp = (
                self.db.client.table("anomaly_scores")
                .select("timestamp,anomaly_score," + ",".join(CONTRIBUTION_COLS))
                .eq("city", city)
                .gte("timestamp", since)
                .order("timestamp", desc=False)
                .execute()
            )
            if resp.data:
                df = pd.DataFrame(resp.data)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                return df
        except Exception as e:
            logger.error("[%s] fetch_scores failed: %s", city, e)
        return pd.DataFrame()

    def check_score_distribution(self, city: str, hours: int = 24) -> Dict[str, Any]:
        """Checks anomaly score statistics for pathological patterns.

        Returns:
            Dict with status ('ok'/'warn'/'error'), mean, std, and issues list.
        """
        df = self._fetch_scores(city, hours)
        result: Dict[str, Any] = {"city": city, "status": "ok", "issues": [], "rows": len(df)}

        if df.empty or "anomaly_score" not in df.columns:
            result["status"] = "no_data"
            result["issues"].append("No anomaly scores in last 24 hours")
            return result

        scores = df["anomaly_score"].dropna().values
        if len(scores) == 0:
            result["status"] = "no_data"
            result["issues"].append("anomaly_score column is all null")
            return result

        mean = float(np.mean(scores))
        std  = float(np.std(scores))
        result["mean"] = round(mean, 4)
        result["std"]  = round(std, 4)

        if mean > SCORE_MEAN_HIGH:
            result["status"] = "warn"
            result["issues"].append(
                f"Score mean {mean:.3f} > {SCORE_MEAN_HIGH} — model always alerting"
            )
        if mean < SCORE_MEAN_LOW:
            result["status"] = "warn"
            result["issues"].append(
                f"Score mean {mean:.3f} < {SCORE_MEAN_LOW} — model may not be detecting"
            )
        if std < SCORE_STD_MIN:
            result["status"] = "warn"
            result["issues"].append(
                f"Score std {std:.4f} < {SCORE_STD_MIN} — scores not varying (model stuck?)"
            )

        return result

    def check_channel_contributions(self, city: str, hours: int = 24) -> Dict[str, Any]:
        """Checks if one channel dominates anomaly contributions (sensor fault signal).

        Returns:
            Dict with dominant_channel if found, and its average share.
        """
        df = self._fetch_scores(city, hours)
        result: Dict[str, Any] = {"city": city, "dominant_channel": None, "issues": []}

        if df.empty:
            return result

        available = [c for c in CONTRIBUTION_COLS if c in df.columns]
        if not available:
            return result

        means = df[available].mean()
        total = means.sum()
        if total == 0:
            return result

        shares = means / total
        dominant = shares.idxmax()
        dominant_share = float(shares[dominant])

        result["shares"] = {c: round(float(shares[c]), 3) for c in available}

        if dominant_share > CONTRIB_DOMINANT:
            result["dominant_channel"] = dominant
            result["issues"].append(
                f"{dominant} accounts for {dominant_share:.0%} of anomaly score "
                f"— possible sensor calibration issue"
            )

        return result

    def compute_psi(self, city: str) -> Dict[str, float]:
        """Computes PSI for anomaly_score comparing last 7 days vs prior 7 days.

        Returns:
            Dict mapping 'anomaly_score' to its PSI value.
        """
        try:
            now   = datetime.now(timezone.utc)
            mid   = (now - timedelta(days=7)).isoformat()
            start = (now - timedelta(days=14)).isoformat()

            resp_recent = (
                self.db.client.table("anomaly_scores")
                .select("anomaly_score")
                .eq("city", city)
                .gte("timestamp", mid)
                .execute()
            )
            resp_prev = (
                self.db.client.table("anomaly_scores")
                .select("anomaly_score")
                .eq("city", city)
                .gte("timestamp", start)
                .lt("timestamp", mid)
                .execute()
            )

            recent = np.array([r["anomaly_score"] for r in (resp_recent.data or []) if r["anomaly_score"] is not None])
            prev   = np.array([r["anomaly_score"] for r in (resp_prev.data or []) if r["anomaly_score"] is not None])

            psi = _compute_psi(prev, recent) if len(prev) >= 5 and len(recent) >= 5 else None
            return {"anomaly_score": round(psi, 4) if psi is not None else None}
        except Exception as e:
            logger.error("[%s] PSI computation failed: %s", city, e)
            return {"anomaly_score": None}

    def generate_health_report(self, cities: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generates a full health report for all (or specified) cities.

        Returns:
            Dict: {city: {status, mean, std, issues, psi, dominant_channel}}
        """
        targets = cities or CITY_NAMES
        report: Dict[str, Any] = {}

        for city in targets:
            dist   = self.check_score_distribution(city)
            contribs = self.check_channel_contributions(city)
            psi    = self.compute_psi(city)

            all_issues = dist.get("issues", []) + contribs.get("issues", [])

            psi_val = psi.get("anomaly_score")
            if psi_val is not None:
                if psi_val > PSI_ALERT:
                    all_issues.append(f"PSI {psi_val:.3f} > {PSI_ALERT} — significant drift, consider retraining")
                    if dist.get("status") == "ok":
                        dist["status"] = "warn"
                elif psi_val > PSI_WARN:
                    all_issues.append(f"PSI {psi_val:.3f} > {PSI_WARN} — minor drift detected")

            report[city] = {
                "status":           dist.get("status", "ok"),
                "rows":             dist.get("rows", 0),
                "mean":             dist.get("mean"),
                "std":              dist.get("std"),
                "psi":              psi_val,
                "dominant_channel": contribs.get("dominant_channel"),
                "issues":           all_issues,
            }

        return report


def _print_report(report: Dict[str, Any]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"\nCityPulse Model Health Report — {today}")
    print("━" * 60)

    for city, info in report.items():
        status = info["status"]
        symbol = "✓ OK  " if status == "ok" else ("⚠ WARN" if status == "warn" else "✗ ERR ")
        mean   = f"{info['mean']:.3f}" if info.get("mean") is not None else "n/a"
        std    = f"{info['std']:.3f}"  if info.get("std")  is not None else "n/a"
        psi    = f"{info['psi']:.3f}"  if info.get("psi")  is not None else "n/a"
        rows   = info.get("rows", 0)
        print(f"  {city:<12} {symbol}  mean:{mean}  std:{std}  psi:{psi}  rows:{rows}")
        for issue in info.get("issues", []):
            print(f"    └─ {issue}")

    print("━" * 60)
    warn_cities = [c for c, i in report.items() if i["status"] == "warn"]
    no_data     = [c for c, i in report.items() if i["status"] == "no_data"]
    if warn_cities:
        print(f"Recommendation: Review models for — {', '.join(warn_cities)}")
    if no_data:
        print(f"No data yet for: {', '.join(no_data)} — run more pipeline cycles")
    if not warn_cities and not no_data:
        print("All models healthy — no action required.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Model Monitor")
    parser.add_argument("--city", help="Run report for a single city only")
    args = parser.parse_args()

    monitor = ModelMonitor()
    cities  = [args.city] if args.city else None
    report  = monitor.generate_health_report(cities)
    _print_report(report)
