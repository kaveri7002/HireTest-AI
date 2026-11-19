# backend/app/__init__.py
"""Flask application factory for HireTest AI backend.
Creates the Flask app, registers extensions and blueprints.
"""

from flask import Flask
from flask_socketio import SocketIO
from pymongo import MongoClient
from redis import Redis
from celery import Celery
import os

socketio: SocketIO | None = None
celery: Celery | None = None
mongo: MongoClient | None = None
redis_client: Redis | None = None


def create_app() -> Flask:
    app = Flask(__name__)
    # Load configuration from environment variables or defaults
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret"),
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://mongo:27017/hiretest"),
        REDIS_URL=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        CELERY_BROKER_URL=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        CELERY_RESULT_BACKEND=os.getenv("REDIS_URL", "redis://redis:6379/0"),
    )

    # Initialize extensions
    global socketio, mongo, redis_client, celery
    socketio = SocketIO(app, cors_allowed_origins="*")
    mongo = MongoClient(app.config["MONGO_URI"]).get_default_database()
    redis_client = Redis.from_url(app.config["REDIS_URL"])

    # Celery configuration
    celery = Celery(app.import_name, broker=app.config["CELERY_BROKER_URL"], backend=app.config["CELERY_RESULT_BACKEND"])
    celery.conf.update(app.config)

    # Register a simple health route
    @app.get("/health")
    def health():
        return {"status": "ok"}

    # TODO: Register blueprints for auth, students, recruiters, jobs, testing, etc.
    return app
