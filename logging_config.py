import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Mengatur logging ke file berputar dan konsol."""

    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, 'intrusion_detection.log')

    file_handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Opsional: juga tampilkan log di console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Hindari duplikasi handler
    if app.logger.hasHandlers():
        app.logger.handlers.clear()

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)