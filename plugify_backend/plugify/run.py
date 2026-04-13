"""
Entry point — run with:   python run.py
Production:               gunicorn "run:app" --workers 2
"""

from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=Config.PORT)
