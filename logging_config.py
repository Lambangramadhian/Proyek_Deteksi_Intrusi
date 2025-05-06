import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Mengatur logging ke file berputar dan konsol."""

    # Buat direktori untuk menyimpan file log jika belum ada
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Path untuk file log
    log_path = os.path.join(log_dir, 'intrusion_detection.log')

    # Konfigurasi handler untuk file log dengan rotasi
    file_handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Hindari duplikasi handler
    if app.logger.hasHandlers():
        app.logger.handlers.clear()

    # Tambahkan handler ke logger aplikasi
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)