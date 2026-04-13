"""
Plugify Ranker
--------------
Multi-signal ranking engine. Runs at startup, indexes once, serves forever.

Scoring formula:
  final = (W_sem  × semantic_cosine)
        + (W_tfidf × tfidf_cosine)
        + (W_intent × intent_match)
        + (W_kw    × keyword_match)
        + (W_rating × normalised_rating)
        + rarity_bonus

All weights live in config.py — change them without touching this file.
"""

import json
import logging
import math
import os
from collections import Counter
from typing import Optional

import numpy as np

from app.config import Config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# TF-IDF helpers (pure Python, no sklearn needed)
# ──────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return [w for w in text.lower().replace("-", " ")
            .replace("/", " ")
            .replace(",", " ")
            .split() if len(w) > 1]


def _tfidf_vector(tokens: list[str], idf: dict) -> dict:
    tf = Counter(tokens)
    total = len(tokens) or 1
    return {t: (count / total) * idf.get(t, 1.0) for t, count in tf.items()}


def _cosine(a: dict, b: dict) -> float:
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[k] * b[k] for k in shared)
    na  = math.sqrt(sum(v * v for v in a.values()))
    nb  = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


# ──────────────────────────────────────────────
# Rarity bonus
# ──────────────────────────────────────────────

def _rarity_bonus(ext: dict) -> float:
    installs = ext.get("installs", 999_999)
    rating   = ext.get("rating", 0.0)
    cfg = Config
    if installs < cfg.RARITY_TIER1_INSTALLS and rating >= cfg.RARITY_TIER1_RATING:
        return 0.25
    if installs < cfg.RARITY_TIER2_INSTALLS and rating >= cfg.RARITY_TIER2_RATING:
        return 0.12
    if installs < cfg.RARITY_TIER3_INSTALLS and rating >= cfg.RARITY_TIER3_RATING:
        return 0.06
    return 0.0


# ──────────────────────────────────────────────
# Ranker — singleton, loaded once at app startup
# ──────────────────────────────────────────────

class PlugifyRanker:
    def __init__(self, extensions: list[dict]):
        self.extensions = extensions
        self._build_tfidf_index()
        self._build_semantic_index()

    # ── Build TF-IDF index ──
    def _build_tfidf_index(self):
        corpus = [
            _tokenize(f"{e['name']} {e['description']} {' '.join(e['keywords'])}")
            for e in self.extensions
        ]
        N = len(corpus)
        df: Counter = Counter()
        for doc in corpus:
            df.update(set(doc))

        self._idf = {
            term: math.log((N + 1) / (count + 1)) + 1
            for term, count in df.items()
        }
        self._ext_tfidf_vecs = [
            _tfidf_vector(doc, self._idf) for doc in corpus
        ]
        logger.info(f"TF-IDF index built — {len(self._idf)} unique terms")

    # ── Build semantic index (sentence-transformers) ──
    def _build_semantic_index(self):
        if not Config.USE_SEMANTIC:
            self._semantic_embeddings = None
            logger.info("Semantic search disabled (USE_SEMANTIC=False)")
            return

        cache = Config.EMBEDDINGS_PATH
        texts = [
            f"{e['name']}. {e['description']} {' '.join(e['keywords'])}"
            for e in self.extensions
        ]

        # Load from cache if available (saves ~2s on restart)
        if os.path.exists(cache):
            self._semantic_embeddings = np.load(cache)
            logger.info(f"Loaded cached embeddings from {cache}")
            return

        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(Config.SENTENCE_MODEL)
            self._semantic_embeddings = model.encode(texts, normalize_embeddings=True)
            np.save(cache, self._semantic_embeddings)
            self._sentence_model = model
            logger.info(f"Semantic embeddings built and cached → {cache}")
        except ImportError:
            logger.warning("sentence-transformers not installed — falling back to TF-IDF only")
            self._semantic_embeddings = None

    # ── Score a single query ──
    def rank(self, query: str, intent_category: str) -> list[dict]:
        q_tokens = _tokenize(query)
        q_tfidf  = _tfidf_vector(q_tokens, self._idf)
        q_words  = set(q_tokens)

        # Pre-compute query semantic embedding
        q_sem_vec = None
        if self._semantic_embeddings is not None:
            try:
                from sentence_transformers import SentenceTransformer
                model = getattr(self, "_sentence_model", None) or SentenceTransformer(Config.SENTENCE_MODEL)
                q_sem_vec = model.encode([query], normalize_embeddings=True)[0]
            except Exception as e:
                logger.warning(f"Semantic encoding failed: {e}")

        max_rating   = max(e.get("rating", 0) for e in self.extensions) or 1
        cfg = Config
        scored = []

        for i, ext in enumerate(self.extensions):
            # 1. TF-IDF cosine
            tfidf_sim = _cosine(q_tfidf, self._ext_tfidf_vecs[i])

            # 2. Semantic cosine
            sem_sim = 0.0
            if q_sem_vec is not None:
                sem_sim = float(np.dot(q_sem_vec, self._semantic_embeddings[i]))

            # 3. Intent / category match
            intent_score = 1.0 if ext.get("category", "") == intent_category else 0.0

            # 4. Keyword match (query word coverage in extension keyword list)
            ext_kws = set(kw.lower() for kw in ext.get("keywords", []))
            # Also split multi-word keywords so "color picker" matches "color"
            ext_kw_tokens = set(tok for kw in ext_kws for tok in kw.split())
            kw_score = len(q_words & (ext_kws | ext_kw_tokens)) / max(len(q_words), 1)

            # 5. Normalised rating
            norm_rating = ext.get("rating", 0) / max_rating

            # 6. Rarity bonus
            rarity = _rarity_bonus(ext)

            # Weighted composite
            final = (
                cfg.WEIGHT_SEMANTIC  * sem_sim     +
                cfg.WEIGHT_TFIDF    * tfidf_sim   +
                cfg.WEIGHT_INTENT   * intent_score +
                cfg.WEIGHT_KEYWORD  * kw_score    +
                cfg.WEIGHT_RATING   * norm_rating  +
                rarity
            )

            if final >= cfg.MIN_SCORE_THRESHOLD:
                scored.append({
                    **ext,
                    "score": round(final, 4),
                    "_breakdown": {
                        "semantic":  round(sem_sim, 3),
                        "tfidf":     round(tfidf_sim, 3),
                        "intent":    round(intent_score, 3),
                        "keyword":   round(kw_score, 3),
                        "rating":    round(norm_rating, 3),
                        "rarity":    round(rarity, 3),
                    },
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:cfg.MAX_RESULTS]


# ── Module-level singleton — initialised once when Flask starts ──
_ranker_instance: Optional[PlugifyRanker] = None


def get_ranker() -> PlugifyRanker:
    global _ranker_instance
    if _ranker_instance is None:
        raise RuntimeError("Ranker not initialised — call init_ranker() first")
    return _ranker_instance


def init_ranker() -> PlugifyRanker:
    global _ranker_instance
    with open(Config.DATA_PATH, encoding="utf-8") as f:
        extensions = json.load(f)
    _ranker_instance = PlugifyRanker(extensions)
    logger.info(f"Ranker ready — {len(extensions)} extensions indexed")
    return _ranker_instance
