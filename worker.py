import redis
from rq import Queue
from rq.worker import SimpleWorker
from rq.timeouts import BaseDeathPenalty
from app_factory import create_app  # Import Flask app factory
from predict import make_prediction  # Import prediction function

# Redis connection
redis_connection = redis.StrictRedis(host='localhost', port=6379, db=0)

# DummyDeathPenalty class to avoid using timeouts (especially on Windows)
class DummyDeathPenalty(BaseDeathPenalty):
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

class WorkerWithoutSignals(SimpleWorker):
    """Custom worker class that doesn't install signal handlers."""
    def _install_signal_handlers(self):
        """Override to prevent installing signal handlers in the background thread."""
        pass

def start_worker():
    """Start the worker in a background thread."""
    app, redis_client = create_app()  # Ensure we have the app context

    with app.app_context():
        # Create a queue to listen to default tasks
        queue = Queue('default', connection=redis_connection)

        # Use the custom WorkerWithoutSignals
        worker = WorkerWithoutSignals([queue], connection=redis_connection)
        worker.death_penalty_class = DummyDeathPenalty  # Avoid SIGALRM issues

        # Start the worker and keep it running to process tasks
        worker.work(with_scheduler=False)   