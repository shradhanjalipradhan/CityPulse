"""
alert_engine.py — Finite State Machine (FSM) for per-city anomaly alerting.

States:  NORMAL → SUSPICIOUS → ALERT → CONFIRMED
State stored in Redis. Transitions logged to Supabase alert_events table.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.redis_client import RedisClient
from database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

# FSM transition thresholds
CONSEC_TO_ALERT = 3        # consecutive windows above threshold to reach ALERT
CONSEC_TO_CONFIRMED = 5    # consecutive windows above 1.5× threshold to reach CONFIRMED
CONSEC_TO_NORMAL = 5       # consecutive windows below threshold to return to NORMAL
CONFIRMED_MULTIPLIER = 1.5 # threshold multiplier for CONFIRMED state

# Visit score constants
VISIT_SCORE_BASE_MAX = 100
ANOMALY_WEIGHT = 40        # max penalty from anomaly score
PENALTY = {"NORMAL": 0, "SUSPICIOUS": 10, "ALERT": 20, "CONFIRMED": 35}
PEAK_HOUR_BONUS = 10
PEAK_HOUR_START = 10
PEAK_HOUR_END = 16

REDIS_TTL = 3600  # 1 hour


class AlertEngine:
    """Per-city FSM that tracks anomaly state and computes visit scores."""

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        supabase_client: Optional[SupabaseClient] = None,
    ) -> None:
        self.redis = redis_client or RedisClient()
        self.supabase = supabase_client or SupabaseClient()

    def _get_state(self, city: str) -> Dict[str, Any]:
        """Loads FSM state for a city from Redis, defaulting to NORMAL.

        Args:
            city: City name.

        Returns:
            State dict with keys: fsm_state, consec_above, consec_below.
        """
        key = f"city:{city}:fsm_state"
        state = self.redis.get(key)
        if state is None:
            state = {"fsm_state": "NORMAL", "consec_above": 0, "consec_below": 0}
        return state

    def _save_state(self, city: str, state: Dict[str, Any]) -> None:
        """Persists FSM state to Redis.

        Args:
            city: City name.
            state: State dict to save.
        """
        key = f"city:{city}:fsm_state"
        self.redis.set(key, state, ttl_seconds=REDIS_TTL)

    def _log_transition(
        self,
        city: str,
        from_state: str,
        to_state: str,
        anomaly_score: float,
    ) -> None:
        """Logs a state transition to Supabase alert_events table.

        Args:
            city: City name.
            from_state: Previous FSM state.
            to_state: New FSM state.
            anomaly_score: Score that triggered the transition.
        """
        try:
            self.supabase.client.table("alert_events").insert({
                "city": city,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_state": from_state,
                "to_state": to_state,
                "anomaly_score": anomaly_score,
                "trigger_channel": "lstm_autoencoder",
            }).execute()
            logger.info("[%s] FSM transition: %s → %s (score=%.4f)",
                        city, from_state, to_state, anomaly_score)
        except Exception as e:
            logger.error("[%s] Failed to log FSM transition: %s", city, e)

    def update(
        self,
        city: str,
        anomaly_score: float,
        threshold: float,
    ) -> Dict[str, Any]:
        """Applies FSM transition rules for one new anomaly score observation.

        Args:
            city: City name.
            anomaly_score: Current reconstruction error score.
            threshold: 95th-percentile threshold from training.

        Returns:
            Updated state dict including fsm_state and visit_score.
        """
        state = self._get_state(city)
        current = state["fsm_state"]
        above = anomaly_score > threshold
        above_confirmed = anomaly_score > threshold * CONFIRMED_MULTIPLIER

        if above:
            state["consec_above"] = state.get("consec_above", 0) + 1
            state["consec_below"] = 0
        else:
            state["consec_below"] = state.get("consec_below", 0) + 1
            state["consec_above"] = 0

        new_state = current

        # Recovery to NORMAL (any state)
        if not above and state["consec_below"] >= CONSEC_TO_NORMAL:
            new_state = "NORMAL"

        # Escalation ladder
        elif current == "NORMAL" and above:
            new_state = "SUSPICIOUS"

        elif current == "SUSPICIOUS":
            if above and state["consec_above"] >= CONSEC_TO_ALERT:
                new_state = "ALERT"

        elif current == "ALERT":
            if above_confirmed and state["consec_above"] >= CONSEC_TO_CONFIRMED:
                new_state = "CONFIRMED"

        if new_state != current:
            self._log_transition(city, current, new_state, anomaly_score)

        state["fsm_state"] = new_state
        visit_score = self.compute_visit_score(anomaly_score, threshold, new_state)
        state["visit_score"] = visit_score
        state["last_score"] = anomaly_score
        state["threshold"] = threshold

        self._save_state(city, state)
        return state

    def compute_visit_score(
        self,
        anomaly_score: float,
        threshold: float,
        fsm_state: str,
    ) -> int:
        """Computes a 0–100 visit suitability score for a city.

        Args:
            anomaly_score: Current reconstruction error score.
            threshold: Training threshold for normalisation.
            fsm_state: Current FSM state string.

        Returns:
            Integer visit score clamped to [0, 100].
        """
        # Normalise score relative to threshold (1.0 = at threshold)
        normalized = min(anomaly_score / max(threshold, 1e-9), 2.0)
        base = VISIT_SCORE_BASE_MAX - (normalized * ANOMALY_WEIGHT)

        penalty = PENALTY.get(fsm_state, 0)

        hour = datetime.now(timezone.utc).hour
        bonus = PEAK_HOUR_BONUS if PEAK_HOUR_START <= hour < PEAK_HOUR_END else 0

        score = base - penalty + bonus
        return int(max(0, min(100, round(score))))
