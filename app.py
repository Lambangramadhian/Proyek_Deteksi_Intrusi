import threading
from flask import request, jsonify, current_app
from app_factory import create_app
from predict import make_prediction
from rq import Queue
from worker import redis_connection, start_worker  # Import worker logic
import json

# Create Flask app and Redis client
app, redis_client = create_app()

# Create a Redis queue for background tasks
task_queue = Queue(connection=redis_connection)

# ===================== Routes ===================== #

@app.route("/", methods=["GET"])
def home():
    return "Welcome to the Intrusion Detection API"

@app.route("/favicon.ico")
def favicon():
    return "", 204  # Empty response, no content

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    input_text = data.get("payload", "").strip()  # Get payload from request

    if not input_text:
        return jsonify({"error": "Payload is required"}), 400

    # Get client IP and User-Agent from request
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Unknown")

    # Enqueue the prediction task into Redis Queue (pass input_text, client_ip, user_agent)
    task = task_queue.enqueue(make_prediction, input_text, client_ip, user_agent, job_timeout=None)  # No timeout
    
    return jsonify({"task_id": task.id, "message": "Prediction task started"}), 202

@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    """Check the status of a queued task."""
    task = task_queue.fetch_job(task_id)
    
    if task is None:
        return jsonify({"error": "Task not found"}), 404
    
    if task.is_finished:
        return jsonify({"status": "completed", "result": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "failed", "error": str(task.exc_info)}), 500
    else:
        return jsonify({"status": "in progress"}), 202

# ===================== Redis Subscription Logic ===================== #

def subscribe_to_logs(app):
    """Subscribe to Redis 'moodle_logs' and process each message."""
    pubsub = redis_connection.pubsub()
    
    # Subscribe to 'moodle_logs' channel
    pubsub.subscribe('moodle_logs')
    print("Subscribed to 'moodle_logs' channel...")

    # Start listening to the channel
    for message in pubsub.listen():
        if message['type'] == 'message':  # Only process actual messages
            try:
                # Parse the incoming message as JSON
                data = json.loads(message['data'])
                print(f"Received message: {data}")

                # Extract fields from the message
                payload = data.get('payload', '')
                ip = data.get('ip', 'Unknown')

                # Use Flask app context
                with app.app_context():
                    # Log the received message
                    current_app.logger.info(f"Processing payload from IP {ip}: {payload}")
                    
                    # Call your make_prediction function within app context
                    prediction_result = make_prediction(payload, client_ip=ip)

                    # Log or handle the prediction result
                    current_app.logger.info(f"Prediction result: {prediction_result}")

            except Exception as e:
                print(f"Error processing message: {str(e)}")

# ===================== Main ===================== #

if __name__ == "__main__":
    # Start Redis worker in a background thread
    worker_thread = threading.Thread(target=start_worker)
    worker_thread.daemon = True  # Daemon thread will shut down when the main program exits
    worker_thread.start()

    # Start Redis subscription in another background thread
    subscriber_thread = threading.Thread(target=subscribe_to_logs, args=(app,))
    subscriber_thread.daemon = True  # Daemon thread will shut down when the main program exits
    subscriber_thread.start()

    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)