# =====================
# Library Internal (modul bawaan Python)
# =====================
import os                                           # Untuk mengakses variabel lingkungan dan operasi sistem file
import logging                                      # Modul logging standar Python untuk pencatatan aktivitas aplikasi
from logging.handlers import RotatingFileHandler    # Handler log untuk menyimpan file log yang bisa berputar (rotasi otomatis ketika ukuran file log terlalu besar)

class RawMessageFormatter(logging.Formatter):
    """Formatter untuk mencetak pesan log dalam format sederhana."""
    def format(self, record):
        """Format pesan log dengan waktu, level, dan pesan."""
        created_time = self.formatTime(record, self.datefmt)
        return f"{created_time} - {record.levelname} - {record.getMessage()}"

def setup_logging(app):
    """Mengatur konfigurasi pencatatan untuk aplikasi Flask."""
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'intrusion_detection.log')

    # Mengatur pemformat untuk pesan log    
    formatter = RawMessageFormatter('%(asctime)s - %(levelname)s - %(message)s')

    # Membuat handler untuk file log dengan rotasi
    file_handler = RotatingFileHandler(log_path, maxBytes=10_000_000, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Membuat handler untuk output ke konsol
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    # Mengatur logger aplikasi
    logger = logging.getLogger(app.name)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    # Assign logger to the Flask app
    app.logger = logger