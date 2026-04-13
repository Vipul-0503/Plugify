# Plugify — Chrome Extension Discovery by Intent

## Project structure

```
plugify/
├── app/
│   ├── __init__.py          ← Flask app factory
│   ├── config.py            ← ALL settings (weights, paths, thresholds)
│   ├── data/
│   │   ├── extensions.json  ← extension dataset
│   │   ├── embeddings.npy   ← auto-generated semantic cache
│   │   └── feedback_log.jsonl ← user interaction log
│   ├── routes/
│   │   ├── recommend.py     ← POST /api/recommend
│   │   └── feedback.py      ← POST /api/feedback
│   ├── services/
│   │   ├── ranker.py        ← multi-signal scoring engine
│   │   ├── intent.py        ← rule-based + LLM intent classifier
│   │   └── llm.py           ← Gemini explanation generator
│   └── utils/
│       └── feedback.py      ← JSONL feedback logger
├── frontend/
│   └── static/
│       └── js/
│           └── api.js       ← frontend ↔ backend bridge
├── tests/
│   └── test_ranker.py       ← pytest test suite
├── run.py                   ← entry point
└── requirements.txt
```

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) add Gemini key for AI explanations
export GEMINI_API_KEY=your_key_here

# 3. Run the server
python run.py

# 4. Test it
curl -X POST http://localhost:5000/api/recommend \
     -H "Content-Type: application/json" \
     -d '{"query": "I want to see font name and color when I hover over text"}'
```

## API

### POST /api/recommend
```json
{ "query": "block distracting sites while studying" }
```
Response:
```json
{
  "query": "...",
  "intent": { "category": "productivity", "confidence": 0.8, "method": "fast" },
  "results": [
    {
      "id": "e10",
      "name": "Strict Workflow",
      "score": 0.743,
      "explanation": "...",
      ...
    }
  ],
  "meta": { "total_results": 6, "elapsed_ms": 42.3 }
}
```

### POST /api/feedback
```json
{ "query": "...", "chosen_id": "e10", "position": 0, "feedback_type": "click" }
```

## Ranking formula

```
score = 0.40 × semantic_similarity   (sentence-transformers)
      + 0.25 × tfidf_cosine
      + 0.20 × intent_category_match
      + 0.10 × keyword_overlap
      + 0.05 × normalised_rating
      + rarity_bonus (0.06–0.25 for underrated gems)
```

All weights are in `app/config.py`.

## Running tests

```bash
pytest tests/ -v
```
