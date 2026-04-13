"""
/api/feedback
-------------
POST  { "query", "chosen_id", "position", "feedback_type", "session_id?" }
→     { "status": "ok" }

Logs every interaction so you can later analyse which results users
actually click (implicit signal) and which they rate explicitly.
"""

import logging
from flask import Blueprint, request, jsonify
from app.utils.feedback import log_feedback

logger = logging.getLogger(__name__)
bp     = Blueprint("feedback", __name__)

VALID_TYPES = {"click", "thumbs_up", "thumbs_down"}


@bp.post("/api/feedback")
def feedback():
    data = request.get_json(silent=True) or {}

    query         = (data.get("query") or "").strip()
    chosen_id     = (data.get("chosen_id") or "").strip()
    position      = data.get("position", -1)
    feedback_type = (data.get("feedback_type") or "").strip()
    session_id    = (data.get("session_id") or "").strip()

    if not query or not chosen_id or feedback_type not in VALID_TYPES:
        return jsonify({"error": "Invalid payload"}), 400

    log_feedback(
        query=query,
        chosen_id=chosen_id,
        position=int(position),
        feedback_type=feedback_type,
        session_id=session_id,
    )

    return jsonify({"status": "ok"})
