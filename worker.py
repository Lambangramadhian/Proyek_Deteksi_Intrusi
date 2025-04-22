import os
import time
import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from app_factory import create_app

# Inisialisasi Redis client
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_connection = redis.StrictRedis(host=redis_host, port=redis_port, db=0)

class DummyDeathPenalty(BaseDeathPenalty):
    """Kelas dummy untuk menghindari penanganan sinyal dalam worker RQ."""
    def __enter__(self): pass
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class WorkerWithoutSignals(SimpleWorker):
    """Kelas worker yang tidak menangani sinyal."""
    def _install_signal_handlers(self): pass
    """Override untuk mencegah penanganan sinyal."""
    def teardown(self, *args, **kwargs):
        """Override untuk mencegah penanganan sinyal selama teardown."""
        try:
            super().teardown(*args, **kwargs)
        except redis.exceptions.ConnectionError:
            print("[Worker] Kesalahan Teardown Redis diabaikan.")

def start_worker():
    """Fungsi untuk memulai worker RQ."""
    while True:
        try:
            app, _ = create_app()
            with app.app_context():
                queue = Queue('default', connection=redis_connection)
                worker = WorkerWithoutSignals([queue], connection=redis_connection)
                worker.death_penalty_class = DummyDeathPenalty
                print(f"[Worker] Worker aktif pada Redis {redis_host}:{redis_port}")
                worker.work(with_scheduler=False)
        except redis.exceptions.ConnectionError as e:
            print(f"[Worker] Redis ConnectionError: {e}. Mencoba lagi dalam 5 detik...")
            time.sleep(5)