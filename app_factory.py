from flask import Flask
import os
import redis
from logging_config import setup_logging

def create_app():
    """Fungsi pabrik untuk membuat aplikasi Flask."""
    app = Flask(__name__)

    # Konfigurasi Secret Key
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")

    # Pengaturan koneksi Redis
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

    # Pengaturan logging
    setup_logging(app)

    return app, redis_client