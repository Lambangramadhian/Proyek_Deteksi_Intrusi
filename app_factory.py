from flask import Flask
import os
import redis
from logging_config import setup_logging

def create_app():
    """Fungsi pabrik untuk membuat dan mengonfigurasi aplikasi Flask."""
    app = Flask(__name__)

    # Konfigurasi Secret Key dari variabel lingkungan
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")

    # Pengaturan koneksi Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

    # Pengaturan logging
    setup_logging(app)

    # Mengimpor blueprint setelah aplikasi dibuat
    return app, redis_client