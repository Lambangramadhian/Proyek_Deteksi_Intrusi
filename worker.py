# =====================
# Library Internal (Standard Python)
# =====================
import os                                       # Untuk akses ke environment variable dan path sistem
import time                                     # Untuk penundaan atau pencatatan waktu
from multiprocessing import current_process     # Untuk identifikasi proses aktif (misal: nama proses worker)

# =====================
# Library Eksternal (Third-party)
# =====================
import redis                                    # Redis client – koneksi ke Redis server
from rq import Queue                            # RQ (Redis Queue) – sistem antrean tugas berbasis Redis
from rq.worker import SimpleWorker              # Worker sederhana dari RQ untuk memproses antrean
from rq.timeouts import BaseDeathPenalty        # Timeout handler – menghentikan job yang terlalu lama berjalan

# =====================
# Modul Internal Proyek (Custom)
# =====================
from app_factory import create_app              # Fungsi factory untuk membuat instance aplikasi Flask (konfigurasi dinamis)


# Inisialisasi direktori model dan memuat model serta vectorizer
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_connection = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

class DummyDeathPenalty(BaseDeathPenalty):
    """Kelas dummy death penalty yang tidak melakukan apa-apa."""
    def __enter__(self): pass
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class WorkerWithoutSignals(SimpleWorker):
    """Worker RQ yang tidak menginstal signal handlers untuk menghindari masalah dengan Redis."""
    def _install_signal_handlers(self): pass
    """Mengoverride metode untuk menghindari instalasi signal handlers yang dapat menyebabkan masalah pada Redis."""

    def teardown(self, *args, **kwargs):
        """Override teardown untuk menghindari error saat koneksi Redis terputus."""
        try:
            super().teardown(*args, **kwargs)
        except redis.exceptions.ConnectionError:
            print("[Worker] Teardown Redis ConnectionError ignored.")

def start_worker():
    """Fungsi untuk memulai worker RQ yang akan memproses antrean tugas."""
    while True:
        try:
            print(f"[Worker STARTED] {current_process().name} active")
            app, _ = create_app()
            with app.app_context():
                queue = Queue('default', connection=redis_connection)
                worker = WorkerWithoutSignals([queue], connection=redis_connection)
                worker.death_penalty_class = DummyDeathPenalty
                worker.work(with_scheduler=False)
        except (redis.exceptions.TimeoutError, redis.exceptions.ConnectionError) as e:
            print(f"[Worker] Redis error: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            print(f"[Worker] {current_process().name} stopped by user.")
            break