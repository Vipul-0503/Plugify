"""
/api/recommend
--------------
POST  { "query": "I want to inspect fonts on hover" }
→     { "query", "intent", "results": [...], "meta": {...} }
"""

import time
import logging
from flask import Blueprint, request, jsonify

from app.services.intent import classify_intent
from app.services.ranker import get_ranker
from app.services.llm   import generate_explanations_batch

logger  = logging.getLogger(__name__)
bp      = Blueprint("recommend", __name__)


@bp.post("/api/recommend")
def recommend():
    data  = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()

    if not query:
        return jsonify({"error": "query is required"}), 400
    if len(query) > 500:
        return jsonify({"error": "query too long (max 500 chars)"}), 400

    t0 = time.perf_counter()

    # 1. Classify intent
    intent_result = classify_intent(query)
    category      = intent_result["category"]

    # 2. Rank extensions
    ranker  = get_ranker()
    results = ranker.rank(query, category)

    # 3. Attach LLM / template explanations
    results = generate_explanations_batch(query, results)

    # 4. Strip internal breakdown from response (keep API clean)
    for r in results:
        r.pop("_breakdown", None)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(f"recommend | query='{query}' intent={category} results={len(results)} ms={elapsed_ms}")

    return jsonify({
        "query":   query,
        "intent":  intent_result,
        "results": results,
        "meta": {
            "total_results": len(results),
            "elapsed_ms":    elapsed_ms,
        },
    })
