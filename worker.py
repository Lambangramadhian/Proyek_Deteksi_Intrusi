import os
import time
import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from multiprocessing import current_process

from app_factory import create_app

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_connection = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

class DummyDeathPenalty(BaseDeathPenalty):
    def __enter__(self): pass
    def __exit__(self, exc_type, exc_val, exc_tb): pass

class WorkerWithoutSignals(SimpleWorker):
    def _install_signal_handlers(self): pass

    def teardown(self, *args, **kwargs):
        try:
            super().teardown(*args, **kwargs)
        except redis.exceptions.ConnectionError:
            print("[Worker] Teardown Redis ConnectionError ignored.")

def start_worker():
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