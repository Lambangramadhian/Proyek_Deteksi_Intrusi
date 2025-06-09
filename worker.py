# Import library standar dan eksternal
import os
import time
import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from multiprocessing import current_process

# Import dari modul internal
from app_factory import create_app

# Konfigurasi Redis dari environment
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))

# Koneksi Redis global
redis_connection = redis.StrictRedis(
    host=redis_host,
    port=redis_port,
    db=0,
    decode_responses=True
)

class DummyDeathPenalty(BaseDeathPenalty):
    """Menghindari masalah signal handling di Windows/threading."""
    def __enter__(self): pass
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class WorkerWithoutSignals(SimpleWorker):
    """Custom Worker tanpa install signal handler."""
    def _install_signal_handlers(self): pass

    def teardown(self, *args, **kwargs):
        """Menghindari error saat teardown worker."""
        try:
            super().teardown(*args, **kwargs)
        except redis.exceptions.ConnectionError:
            print("[Worker] Teardown Redis ConnectionError diabaikan.")

def start_worker():
    """Worker Redis auto-reconnect saat Redis crash."""
    while True:
        try:
            print(f"[Worker STARTED] {current_process().name} aktif")
            app, _ = create_app()
            with app.app_context():
                queue = Queue('default', connection=redis_connection)
                worker = WorkerWithoutSignals([queue], connection=redis_connection)
                worker.death_penalty_class = DummyDeathPenalty
                worker.work(with_scheduler=False)

        # Jika Redis tidak dapat terhubung, tunggu dan coba lagi
        except redis.exceptions.TimeoutError as e:
            print(f"[Worker] Redis TimeoutError: {e}. Coba lagi dalam 5 detik...")
            time.sleep(5)
        except redis.exceptions.ConnectionError as e:
            print(f"[Worker] Redis ConnectionError: {e}. Coba lagi dalam 5 detik...")
            time.sleep(5)