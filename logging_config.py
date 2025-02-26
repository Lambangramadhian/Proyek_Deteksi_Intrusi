import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Mengatur logging ke file dengan log yang berputar."""
    handler = RotatingFileHandler('intrusion_detection.log', maxBytes=10000000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)