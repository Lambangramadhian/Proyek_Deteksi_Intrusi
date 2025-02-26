from flask import request, jsonify
from app_factory import create_app
from predict import make_prediction
from rq import Queue
from worker import redis_connection

# Create app and Redis client
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
    input_text = data.get("payload", "").strip()  # Extract the payload from request

    if not input_text:
        return jsonify({"error": "Payload is required"}), 400

    # Get client IP and User-Agent from the request
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Unknown")

    # Offload prediction task to Redis Queue (pass input_text, client_ip, user_agent)
    task = task_queue.enqueue(make_prediction, input_text, client_ip, user_agent, job_timeout=None)  # Disable timeouts
    
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)