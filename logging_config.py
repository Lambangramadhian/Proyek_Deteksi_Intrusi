# logging_config.py
import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Mengatur logging ke file yang berputar (rotating file)."""
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)  # Buat folder logs/ jika belum ada

    # Mengatur penangan file yang berulang-ulang
    log_path = os.path.join(log_dir, 'intrusion_detection.log')
    handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Hapus penangan yang ada untuk menghindari duplikasi log
    if app.logger.hasHandlers():
        app.logger.handlers.clear()

    # Mengatur pencatat untuk menggunakan handler
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)