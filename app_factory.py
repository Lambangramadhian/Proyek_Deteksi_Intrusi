# =====================
# Library Internal (modul bawaan Python & framework utama)
# =====================
import os                                   # Modul OS – untuk akses ke environment variable, path, dsb
import redis                                # Redis client – untuk koneksi ke database Redis (digunakan untuk antrian, cache, dsb)
from flask import Flask                     # Flask – framework utama untuk membuat aplikasi web

# =====================
# Library Eksternal / Kustom (dibuat dalam proyek ini)
# ====================                      
from logging_config import setup_logging    # Fungsi kustom untuk mengatur konfigurasi logging aplikasi

def create_app():
    """Fungsi untuk membuat dan mengonfigurasi aplikasi Flask."""
    app = Flask(__name__)
    
    # Konfigurasi dasar
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")
    
    # Konfigurasi Redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    
    # Validasi koneksi Redis
    try:
        redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        redis_client.ping()  # Validasi koneksi awal
    except redis.ConnectionError as e:
        raise RuntimeError(f"Redis connection failed: {e}")
    
    # Setup logging
    setup_logging(app)
    return app, redis_client