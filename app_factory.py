from flask import Flask
import os
import redis
from logging_config import setup_logging

def create_app():
    """Factory function to create and configure the Flask app."""
    app = Flask(__name__)

    # Config Secret Key from environment variable
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")

    # Redis connection setup
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

    # Setup logging
    setup_logging(app)

    # Return the app and redis_client
    return app, redis_client    