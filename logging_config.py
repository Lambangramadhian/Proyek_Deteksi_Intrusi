import logging
from logging.handlers import RotatingFileHandler

def setup_logging(app):
    # General logging
    log_handler = RotatingFileHandler("api.log", maxBytes=5000000, backupCount=5)
    log_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    log_handler.setFormatter(formatter)

    # Security-specific logging
    security_handler = RotatingFileHandler("security.log", maxBytes=5000000, backupCount=5)
    security_handler.setLevel(logging.WARNING)

    app.logger.addHandler(log_handler)
    app.logger.addHandler(security_handler)