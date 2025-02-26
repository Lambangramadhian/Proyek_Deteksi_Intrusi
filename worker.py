import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from app_factory import create_app  # Impor pabrik aplikasi Flask
from predict import make_prediction  # Impor fungsi prediksi

# Koneksi Redis
redis_connection = redis.StrictRedis(host='localhost', port=6379, db=0)

# DummyDeathPenalty Kustom untuk menghindari penggunaan timeout
class DummyDeathPenalty(BaseDeathPenalty):
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

if __name__ == '__main__':
    # Dorong konteks aplikasi Flask untuk memungkinkan penggunaan current_app dalam tugas
    app, redis_client = create_app()

    with app.app_context():
        # Buat pekerja untuk antrean default
        queue = Queue('default', connection=redis_connection)
        
        # Gunakan SimpleWorker dengan kelas death penalty kustom
        worker = SimpleWorker([queue], connection=redis_connection)
        
        # Tetapkan DummyDeathPenalty untuk menghindari masalah SIGALRM pada Windows
        worker.death_penalty_class = DummyDeathPenalty
        
        # Jalankan pekerja (tetap berjalan untuk memproses tugas)
        worker.work(with_scheduler=False)