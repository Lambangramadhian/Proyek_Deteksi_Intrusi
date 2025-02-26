import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    """Set up logging to a file with rotating logs."""
    handler = RotatingFileHandler('intrusion_detection.log', maxBytes=10000000, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)