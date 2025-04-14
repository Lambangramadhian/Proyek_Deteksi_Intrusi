import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Mengatur logging ke file yang berputar (rotating file)."""
    handler = RotatingFileHandler('logs/intrusion_detection.log', maxBytes=10000000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Bersihkan handler yang ada untuk menghindari log duplikat
    if app.logger.hasHandlers():
        app.logger.handlers.clear()

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)