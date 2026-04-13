"""
Feedback Logger
---------------
Appends user feedback events to a JSONL file.
Each line is one JSON object — easy to read, stream, and later train on.

This is the seed for future personalization and learning-to-rank.
"""

import json
import logging
import os
from datetime import datetime, timezone

from app.config import Config

logger = logging.getLogger(__name__)


def log_feedback(
    query: str,
    chosen_id: str,
    position: int,
    feedback_type: str,          # "click" | "thumbs_up" | "thumbs_down"
    session_id: str = "",
):
    """
    Append one feedback event to the JSONL log.

    Args:
        query        — the user's original query string
        chosen_id    — extension ID that was clicked / rated
        position     — 0-indexed rank position of the chosen result
        feedback_type — "click", "thumbs_up", or "thumbs_down"
        session_id   — optional client-side session identifier
    """
    record = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "query":         query,
        "chosen_id":     chosen_id,
        "position":      position,
        "feedback_type": feedback_type,
        "session_id":    session_id,
    }

    try:
        os.makedirs(os.path.dirname(Config.FEEDBACK_PATH), exist_ok=True)
        with open(Config.FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logger.debug(f"Feedback logged: {feedback_type} on {chosen_id} at pos {position}")
    except Exception as e:
        logger.error(f"Failed to log feedback: {e}")


def read_feedback(limit: int = 500) -> list[dict]:
    """Return the most recent `limit` feedback records (for analytics)."""
    if not os.path.exists(Config.FEEDBACK_PATH):
        return []
    with open(Config.FEEDBACK_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    return [json.loads(l) for l in lines[-limit:] if l.strip()]
