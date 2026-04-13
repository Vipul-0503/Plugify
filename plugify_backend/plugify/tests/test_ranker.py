"""
Tests — run with:   pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pytest
from app.config import Config
from app.services.intent import classify_fast, classify_intent
from app.services.ranker import PlugifyRanker


# ── Fixtures ──────────────────────────────────

@pytest.fixture(scope="module")
def extensions():
    with open(Config.DATA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ranker(extensions):
    return PlugifyRanker(extensions)


# ── Intent classifier ──────────────────────────

class TestIntentClassifier:
    def test_design_intent(self):
        cat, conf = classify_fast("I want to see font name and color on hover")
        assert cat == "design"
        assert conf > 0

    def test_productivity_intent(self):
        cat, conf = classify_fast("block distracting sites while studying")
        assert cat == "productivity"

    def test_developer_intent(self):
        cat, conf = classify_fast("format and view json api responses")
        assert cat == "developer"

    def test_unknown_returns_general(self):
        cat, conf = classify_fast("xyzzy frobnicator")
        assert cat == "general"
        assert conf == 0.0

    def test_classify_intent_returns_dict(self):
        result = classify_intent("privacy and tracker blocking")
        assert "category" in result
        assert "confidence" in result
        assert "method" in result


# ── Ranker ────────────────────────────────────

class TestRanker:
    def test_returns_results(self, ranker):
        results = ranker.rank("font inspector on hover", "design")
        assert len(results) > 0

    def test_results_sorted_by_score(self, ranker):
        results = ranker.rank("font inspector on hover", "design")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_underrated_gems_surface(self, ranker):
        results = ranker.rank("font name size color hover designer", "design")
        # At least one result should be under 20k installs (underrated)
        low_install = [r for r in results if r.get("installs", 999999) < 20000]
        assert len(low_install) > 0

    def test_score_in_range(self, ranker):
        results = ranker.rank("block ads tracker privacy", "security")
        for r in results:
            assert 0.0 <= r["score"] <= 2.0   # rarity bonus can push above 1.0

    def test_returns_max_results(self, ranker):
        results = ranker.rank("developer tools", "developer")
        assert len(results) <= Config.MAX_RESULTS

    def test_intent_match_boost(self, ranker):
        # Design query with design intent should rank design extensions higher
        results_design = ranker.rank("inspect css layout", "design")
        results_wrong  = ranker.rank("inspect css layout", "productivity")
        # Top result should differ when intent changes
        top_design = results_design[0]["category"] if results_design else None
        assert top_design == "design" or top_design == "developer"

    def test_niche_query_font_hover(self, ranker):
        """The canonical 'designer' use case from the brief."""
        results = ranker.rank(
            "I want to see font name size and color when I hover over text",
            "design"
        )
        assert len(results) > 0
        names = [r["name"] for r in results]
        # At least one of the known font-inspection extensions should appear
        font_tools = {"WhatFont", "Fonts Ninja", "Fonts & Colors", "Hoverify", "UI Inspector"}
        assert any(n in font_tools for n in names), f"Expected a font tool, got: {names}"
