import os
import logging
from logging.handlers import RotatingFileHandler

class RawMessageFormatter(logging.Formatter):
    def format(self, record):
        created_time = self.formatTime(record, self.datefmt)
        return f"{created_time} - {record.levelname} - {record.getMessage()}"

def setup_logging(app):
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'intrusion_detection.log')

    formatter = RawMessageFormatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger(app.name)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    app.logger = logger