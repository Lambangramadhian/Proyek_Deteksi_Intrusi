# =====================
# Library Standar Python
# =====================
import os                                   # Modul OS – untuk akses ke environment variable dan operasi sistem file

# =====================
# Library Eksternal (Pihak Ketiga)
# =====================
import redis                                # Redis client – untuk koneksi ke database Redis (digunakan untuk antrean, cache, dsb.)
from flask import Flask                     # Flask – framework web utama untuk membangun aplikasi berbasis HTTP

# =====================
# Modul Internal Proyek (Custom Module)
# =====================
from logging_config import setup_logging    # Fungsi untuk mengatur konfigurasi logging aplikasi dari modul internal

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