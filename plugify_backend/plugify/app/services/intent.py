"""
Intent Classifier
-----------------
Two-tier classification:
  1. Fast rule-based path   — zero latency, covers common queries
  2. Gemini LLM fallback    — for ambiguous or novel queries

Add new categories by extending INTENT_MAP only — no other file needs changing.
"""

import os
import logging
from app.config import Config

logger = logging.getLogger(__name__)

# ── Keyword map — extend freely ──
INTENT_MAP: dict[str, list[str]] = {
    "design": [
        "font", "color", "colour", "css", "design", "ui", "ux", "uiux",
        "pixel", "layout", "spacing", "inspect", "hover", "typography",
        "palette", "hex", "rgb", "hsl", "responsive", "grid", "ruler",
        "mockup", "prototype", "visual", "graphic", "figma", "sketch",
        "wireframe", "brand", "style guide", "designer", "eyedropper",
        "weight", "line height", "border", "padding", "margin",
    ],
    "developer": [
        "code", "developer", "json", "api", "http", "request", "debug",
        "devtools", "react", "angular", "vue", "performance", "audit",
        "seo", "network", "proxy", "mock", "intercept", "frontend",
        "backend", "tech stack", "framework", "cms", "redirect", "headers",
        "regex", "snippet", "github", "console", "error", "breakpoint",
    ],
    "productivity": [
        "focus", "block", "distract", "pomodoro", "timer", "habit", "study",
        "work", "tab", "session", "workspace", "goal", "schedule", "reminder",
        "task", "todo", "time management", "productivity", "snooze", "deep work",
        "mindful", "intention", "procrastinate",
    ],
    "security": [
        "privacy", "password", "block", "tracker", "vpn", "https", "secure",
        "ad", "phishing", "encrypt", "anonymous", "disposable", "temp mail",
        "safe", "malware", "cookie", "fingerprint", "eff", "tracking",
    ],
    "writing": [
        "grammar", "spell", "write", "essay", "proofread", "paraphrase",
        "rewrite", "readability", "editor", "language", "tone", "clarity",
        "passive voice", "wordtune", "grammarly", "plagiarism",
    ],
    "research": [
        "annotate", "highlight", "save", "note", "academic", "citation",
        "pdf", "research", "reference", "read", "bookmark", "library",
        "zotero", "spaced repetition", "knowledge", "article",
    ],
    "accessibility": [
        "dyslexia", "screen reader", "accessibility", "zoom", "contrast",
        "dark mode", "vision", "font size", "color blind", "tts",
        "read aloud", "magnify", "high contrast",
    ],
}


def classify_fast(query: str) -> tuple[str, float]:
    """
    Rule-based classifier. Returns (category, confidence_score).
    Confidence is normalised hit count; 0.0 means no match.
    """
    q = query.lower()
    scores: dict[str, int] = {}

    for category, keywords in INTENT_MAP.items():
        hits = sum(1 for kw in keywords if kw in q)
        if hits:
            scores[category] = hits

    if not scores:
        return "general", 0.0

    best_cat = max(scores, key=scores.__getitem__)
    total_hits = sum(scores.values())
    confidence = scores[best_cat] / total_hits if total_hits else 0.0
    return best_cat, confidence


def classify_with_llm(query: str) -> str:
    """
    Gemini-based fallback. Only called when rule-based confidence is low.
    Requires GEMINI_API_KEY in environment.
    """
    if not Config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — returning 'general'")
        return "general"

    try:
        import google.generativeai as genai
        genai.configure(api_key=Config.GEMINI_API_KEY)
        model = genai.GenerativeModel(Config.GEMINI_MODEL)

        categories = list(INTENT_MAP.keys()) + ["general"]
        prompt = (
            f"Classify this Chrome extension search query into exactly one category.\n"
            f"Query: \"{query}\"\n"
            f"Categories: {', '.join(categories)}\n"
            f"Reply with only the category name, nothing else."
        )
        response = model.generate_content(prompt)
        result = response.text.strip().lower()
        return result if result in categories else "general"

    except Exception as e:
        logger.error(f"LLM classification failed: {e}")
        return "general"


def classify_intent(query: str) -> dict:
    """
    Public interface — always call this.
    Returns: { "category": str, "confidence": float, "method": "fast"|"llm" }
    """
    category, confidence = classify_fast(query)

    # Fall back to LLM when rule-based is uncertain
    if confidence < 0.4 or category == "general":
        llm_category = classify_with_llm(query)
        return {
            "category": llm_category,
            "confidence": 0.75,   # LLM assumed higher confidence
            "method": "llm",
        }

    return {
        "category": category,
        "confidence": round(confidence, 3),
        "method": "fast",
    }
