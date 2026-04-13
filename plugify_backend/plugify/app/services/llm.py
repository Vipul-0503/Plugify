"""
LLM Service (Gemini)
--------------------
Generates human-readable explanations for why each extension matches
the user's query. Falls back to a template when API key is absent.

Keeping LLM calls isolated here means you can swap Gemini → OpenAI
by editing only this file.
"""

import logging
from app.config import Config

logger = logging.getLogger(__name__)


# ── Template fallback (no API key needed) ──
def _template_explanation(query: str, ext: dict) -> str:
    breakdown = ext.get("_breakdown", {})
    kws = ext.get("keywords", [])[:3]
    category = ext.get("category", "general")
    installs = ext.get("installs", 0)

    category_audience = {
        "design":        "UI/UX and graphic designers",
        "developer":     "developers and engineers",
        "productivity":  "people focused on deep work",
        "security":      "privacy-conscious users",
        "writing":       "writers and editors",
        "research":      "researchers and students",
        "accessibility": "users with accessibility needs",
    }

    audience = category_audience.get(category, "power users")
    rarity_note = (
        f" Fewer than {installs:,} people use it — so it's a hidden gem."
        if installs < 20_000 else ""
    )

    if breakdown.get("keyword", 0) > 0.3:
        return (
            f"Directly solves your request — it handles <strong>{', '.join(kws)}</strong>, "
            f"which are the core capabilities you described.{rarity_note}"
        )
    if breakdown.get("rarity", 0) > 0.1:
        return (
            f"A favourite among {audience} for exactly this workflow, "
            f"yet rarely discovered through regular search.{rarity_note}"
        )
    if breakdown.get("intent", 0) > 0.5:
        return (
            f"Matches your intent category (<em>{category}</em>) and covers "
            f"<strong>{', '.join(kws[:2])}</strong> — the features implied by your query.{rarity_note}"
        )
    return (
        f"Semantically similar to your goal — it provides <strong>{', '.join(kws[:2])}</strong> "
        f"which overlaps with what you described.{rarity_note}"
    )


# ── Gemini explanation ──
def _gemini_explanation(query: str, ext: dict) -> str:
    import google.generativeai as genai
    genai.configure(api_key=Config.GEMINI_API_KEY)
    model = genai.GenerativeModel(Config.GEMINI_MODEL)

    prompt = (
        f"You are inside Plugify, a Chrome extension recommender that surfaces underrated gems.\n\n"
        f"User's goal: \"{query}\"\n"
        f"Recommended extension: {ext['name']}\n"
        f"Description: {ext['description']}\n"
        f"Category: {ext.get('category', '')}\n"
        f"Install count: {ext.get('installs', 0):,}\n\n"
        f"Write 1–2 sentences explaining specifically WHY this extension matches what the user wants. "
        f"Be concrete, mention the user's actual goal, highlight if it's an underrated pick. "
        f"Use HTML bold tags for key terms. Do NOT start with 'This extension'."
    )

    response = model.generate_content(prompt)
    return response.text.strip()


# ── Public interface ──
def generate_explanation(query: str, ext: dict) -> str:
    """
    Returns an HTML explanation string.
    Uses Gemini if key is available, otherwise falls back to templates.
    """
    if Config.GEMINI_API_KEY:
        try:
            return _gemini_explanation(query, ext)
        except Exception as e:
            logger.warning(f"Gemini explanation failed for '{ext['name']}': {e}")

    return _template_explanation(query, ext)


def generate_explanations_batch(query: str, results: list[dict]) -> list[dict]:
    """
    Attach explanations to top N results. Remaining results get templates.
    Modifies results in-place and returns the list.
    """
    top_n = Config.LLM_EXPLANATION_TOP_N

    for i, ext in enumerate(results):
        if i < top_n:
            ext["explanation"] = generate_explanation(query, ext)
        else:
            ext["explanation"] = _template_explanation(query, ext)

    return results
