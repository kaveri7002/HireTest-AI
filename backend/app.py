# backend/app.py
"""Entry point for the Flask backend.
Run with:
    python -m backend.app
or via gunicorn / Docker.
"""
from . import create_app, socketio

app = create_app()

if __name__ == "__main__":
    # Development server (not for production)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
