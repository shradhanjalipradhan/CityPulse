"""
health_check.py — Checks all 5 CityPulse components and prints a status report.

Components checked:
  1. Supabase   — can query anomaly_scores, returns latest row age
  2. Redis       — all 8 city state keys present
  3. HF Space    — /health endpoint responds 200
  4. Kafka topic — producer can connect (SASL_SSL)
  5. Airflow     — local Docker container running (optional)

Usage:
  python monitoring/health_check.py
  python monitoring/health_check.py --json   # output as JSON
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

logging.basicConfig(level=logging.WARNING)

CITY_NAMES = [
    "Zurich", "Geneva", "Bern", "Lucerne",
    "Basel", "Interlaken", "Lausanne", "Zermatt",
]


# ── Component checks ──────────────────────────────────────────────────────────

def check_supabase() -> Dict[str, Any]:
    """Queries anomaly_scores for the most recent row across all cities."""
    try:
        from supabase import create_client
        client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
        t0 = time.time()
        resp = (
            client.table("anomaly_scores")
            .select("city,timestamp,anomaly_score,fsm_state,visit_score")
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        latency_ms = round((time.time() - t0) * 1000)

        if resp.data:
            row = resp.data[0]
            ts  = row.get("timestamp", "")
            try:
                from dateutil import parser as dp
                age_minutes = round(
                    (datetime.now(timezone.utc) - dp.parse(ts)).total_seconds() / 60, 1
                )
            except Exception:
                age_minutes = None
            return {
                "status": "ok",
                "latency_ms": latency_ms,
                "latest_row_age_minutes": age_minutes,
                "latest_city": row.get("city"),
                "latest_fsm":  row.get("fsm_state"),
            }
        return {"status": "warn", "message": "anomaly_scores table is empty"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_redis() -> Dict[str, Any]:
    """Checks that all 8 city:*:state keys exist in Upstash Redis."""
    try:
        base_url = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/").strip('"')
        token    = os.environ["UPSTASH_REDIS_REST_TOKEN"].strip('"')
        headers  = {"Authorization": f"Bearer {token}"}

        cities_found = []
        cities_missing = []

        t0 = time.time()
        for city in CITY_NAMES:
            r = requests.get(
                f"{base_url}/get/city:{city}:state",
                headers=headers,
                timeout=5,
            )
            if r.status_code == 200 and r.json().get("result"):
                cities_found.append(city)
            else:
                cities_missing.append(city)
        latency_ms = round((time.time() - t0) * 1000)

        status = "ok" if not cities_missing else ("warn" if cities_found else "error")
        return {
            "status": status,
            "latency_ms": latency_ms,
            "cities_cached": len(cities_found),
            "missing": cities_missing if cities_missing else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_hf_space() -> Dict[str, Any]:
    """Calls the HuggingFace Space /health endpoint."""
    try:
        hf_user  = os.environ.get("HF_USERNAME", "")
        hf_space = os.environ.get("HF_SPACE_NAME", "")
        endpoint = f"https://{hf_user}-{hf_space}.hf.space"

        t0 = time.time()
        r  = requests.get(f"{endpoint}/health", timeout=15)
        latency_ms = round((time.time() - t0) * 1000)

        if r.status_code == 200:
            data = r.json()
            return {
                "status": "ok",
                "latency_ms": latency_ms,
                "models_loaded": data.get("models_loaded", "?"),
                "endpoint": endpoint,
            }
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": r.status_code,
            "endpoint": endpoint,
        }
    except requests.Timeout:
        return {"status": "error", "message": "HF Space timeout (>15s) — space may be sleeping"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_kafka() -> Dict[str, Any]:
    """Verifies Kafka broker connectivity via a metadata fetch."""
    try:
        from confluent_kafka import Producer
        conf = {
            "bootstrap.servers":  os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "security.protocol":  "SASL_SSL",
            "sasl.mechanism":     "SCRAM-SHA-256",
            "sasl.username":      os.environ["KAFKA_API_KEY"],
            "sasl.password":      os.environ["KAFKA_API_SECRET"],
            "socket.timeout.ms":  5000,
        }
        t0 = time.time()
        p  = Producer(conf)
        md = p.list_topics(timeout=5)
        latency_ms = round((time.time() - t0) * 1000)
        topic = os.environ.get("KAFKA_TOPIC_SENSOR", "raw-sensor-data")
        topic_ok = topic in md.topics
        return {
            "status": "ok" if topic_ok else "warn",
            "latency_ms": latency_ms,
            "topic": topic,
            "topic_found": topic_ok,
            "broker_count": len(md.brokers),
        }
    except ImportError:
        return {"status": "skip", "message": "confluent_kafka not installed in this env"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_airflow() -> Dict[str, Any]:
    """Checks if the Airflow Docker container is running locally."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", "airflow"],
            capture_output=True, text=True, timeout=5,
        )
        status = result.stdout.strip()
        if status == "running":
            return {"status": "ok", "container": "airflow", "state": "running"}
        elif status:
            return {"status": "warn", "container": "airflow", "state": status}
        return {"status": "skip", "message": "Airflow container not found"}
    except FileNotFoundError:
        return {"status": "skip", "message": "Docker not available in PATH"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Full system check ─────────────────────────────────────────────────────────

def run_health_check() -> Dict[str, Any]:
    """Runs all component checks and returns a structured health report."""
    print("Checking CityPulse components...", flush=True)

    components = {
        "supabase": check_supabase(),
        "redis":    check_redis(),
        "hf_space": check_hf_space(),
        "kafka":    check_kafka(),
        "airflow":  check_airflow(),
    }

    all_statuses = [c["status"] for c in components.values()]
    if any(s == "error" for s in all_statuses):
        overall = "degraded"
    elif any(s == "warn" for s in all_statuses):
        overall = "warning"
    else:
        overall = "healthy"

    return {
        "status":    overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


def _print_report(report: Dict[str, Any]) -> None:
    status_symbol = {"ok": "✓", "warn": "⚠", "error": "✗", "skip": "–", "healthy": "✓", "degraded": "✗", "warning": "⚠"}
    overall = report["status"]
    print(f"\nCityPulse System Health — {report['timestamp'][:19]} UTC")
    print("━" * 55)
    print(f"  Overall status: {status_symbol.get(overall, '?')} {overall.upper()}")
    print()

    for name, info in report["components"].items():
        sym  = status_symbol.get(info["status"], "?")
        stat = info["status"].upper()

        extras = []
        if "latency_ms" in info:
            extras.append(f"latency={info['latency_ms']}ms")
        if "latest_row_age_minutes" in info and info["latest_row_age_minutes"] is not None:
            extras.append(f"last_row={info['latest_row_age_minutes']}min ago")
        if "cities_cached" in info:
            extras.append(f"cities={info['cities_cached']}/8")
        if "models_loaded" in info:
            extras.append(f"models={info['models_loaded']}")
        if "topic_found" in info:
            extras.append(f"topic={'ok' if info['topic_found'] else 'missing'}")
        if "state" in info:
            extras.append(f"container={info['state']}")
        if "message" in info:
            extras.append(info["message"])
        if "missing" in info and info["missing"]:
            extras.append(f"missing={info['missing']}")

        extra_str = "  " + " · ".join(extras) if extras else ""
        print(f"  {sym} {name:<12} {stat:<8}{extra_str}")

    print("━" * 55)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CityPulse Health Check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    report = run_health_check()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    sys.exit(0 if report["status"] == "healthy" else 1)
