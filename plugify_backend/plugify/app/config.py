import os

class Config:
    # ── Paths ──
    BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_PATH      = os.path.join(BASE_DIR, "app", "data", "extensions.json")
    EMBEDDINGS_PATH = os.path.join(BASE_DIR, "app", "data", "embeddings.npy")
    FEEDBACK_PATH  = os.path.join(BASE_DIR, "app", "data", "feedback_log.jsonl")

    # ── Ranking weights (must sum to 1.0) ──
    WEIGHT_SEMANTIC  = 0.40
    WEIGHT_TFIDF     = 0.25
    WEIGHT_INTENT    = 0.20
    WEIGHT_KEYWORD   = 0.10
    WEIGHT_RATING    = 0.05

    # ── Rarity thresholds ──
    RARITY_TIER1_INSTALLS = 10_000   # bonus: 0.25
    RARITY_TIER1_RATING   = 4.0
    RARITY_TIER2_INSTALLS = 30_000   # bonus: 0.12
    RARITY_TIER2_RATING   = 4.2
    RARITY_TIER3_INSTALLS = 50_000   # bonus: 0.06
    RARITY_TIER3_RATING   = 4.3

    # ── Result limits ──
    MAX_RESULTS          = 6
    MIN_SCORE_THRESHOLD  = 0.02

    # ── LLM ──
    GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "AIzaSyCUclKynXbssO2oS6a_atFrlKpTd7Jo2iQ")
    GEMINI_MODEL         = "gemini-1.5-flash"
    LLM_EXPLANATION_TOP_N = 3        # only generate LLM explanations for top N results

    # ── Semantic model ──
    SENTENCE_MODEL       = "all-MiniLM-L6-v2"
    USE_SEMANTIC         = True       # set False to fall back to TF-IDF only (no GPU needed)

    # ── Flask ──
    DEBUG                = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PORT                 = int(os.getenv("PORT", 5000))
    CORS_ORIGINS         = ["*"]
