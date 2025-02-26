import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from app_factory import create_app  # Import the Flask app factory
from predict import make_prediction  # Import the prediction function

# Redis connection
redis_connection = redis.StrictRedis(host='localhost', port=6379, db=0)

# Custom DummyDeathPenalty to avoid using timeouts
class DummyDeathPenalty(BaseDeathPenalty):
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

if __name__ == '__main__':
    # Push Flask app context to allow current_app usage in jobs
    app, redis_client = create_app()

    with app.app_context():
        # Create a worker for the default queue
        queue = Queue('default', connection=redis_connection)
        
        # Use SimpleWorker with custom death penalty class
        worker = SimpleWorker([queue], connection=redis_connection)
        
        # Set DummyDeathPenalty to avoid SIGALRM issues on Windows
        worker.death_penalty_class = DummyDeathPenalty
        
        # Start the worker (keep it running to process tasks)
        worker.work(with_scheduler=False)