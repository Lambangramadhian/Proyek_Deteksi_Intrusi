import os
import redis
from flask import Flask
from logging_config import setup_logging

def create_app():
    app = Flask(__name__)
    
    # Konfigurasi dasar
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")
    
    # Konfigurasi Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    try:
        redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        redis_client.ping()  # Validasi koneksi awal
    except redis.ConnectionError as e:
        raise RuntimeError(f"Redis connection failed: {e}")
    
    setup_logging(app)
    return app, redis_client