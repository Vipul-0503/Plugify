"""
App Factory
-----------
Flask uses the factory pattern so the app can be created with
different configs (testing, production) without side effects.
"""

import logging
from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.services.ranker import init_ranker


def create_app() -> Flask:
    app = Flask(__name__)

    # ── Logging ──
    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ── CORS (allows the frontend to call the API from a different origin) ──
    CORS(app, origins=Config.CORS_ORIGINS)

    # ── Initialise ranker once at startup ──
    init_ranker()

    # ── Register blueprints ──
    from app.routes.recommend import bp as recommend_bp
    from app.routes.feedback  import bp as feedback_bp

    app.register_blueprint(recommend_bp)
    app.register_blueprint(feedback_bp)

    # ── Health check ──
    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "plugify"}

    return app
