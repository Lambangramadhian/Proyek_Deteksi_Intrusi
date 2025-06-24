import json
import time
import redis
import urllib.parse
import datetime
import multiprocessing
import hashlib
from flask import request, jsonify, current_app
from multiprocessing import Process, current_process
from rq import Queue
from rq.job import Job

from app_factory import create_app
from predict import make_prediction
from worker import start_worker
from utils import flatten_dict, parse_payload, mask_sensitive_fields, mask_url_query, mask_inline_sensitive_fields

app, redis_connection = create_app()
task_queue = Queue(connection=redis_connection)

@app.route("/", methods=["GET"])
def home():
    return "Selamat datang di API Deteksi Intrusi"

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    payload = data.get("payload", {})
    method = payload.get("method", "")
    url = payload.get("url", "")
    body = payload.get("body", "")
    client_ip = request.remote_addr

    if not method or not url:
        return jsonify({"error": "Method dan URL diperlukan"}), 400

    task = task_queue.enqueue(make_prediction, method, url, body, client_ip, job_timeout=None)
    current_app.logger.info(f"Enqueued task: {task.id}")
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    task: Job = task_queue.fetch_job(task_id)
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202

def handle_pubsub_message(data):
    ip = data.get("ip_address") or data.get("ip") or "Tidak Diketahui"
    method = data.get("method", "").upper()
    url = urllib.parse.unquote(data.get("url", ""))
    url = mask_url_query(url)

    raw_payload = data.get("payloadData") or data.get("payload")
    payload_body = parse_payload(raw_payload, url=url, ip=ip, logger=current_app.logger)

    flat_body = flatten_dict(payload_body)
    flat_body.pop("raw", None)

    decoded_and_cleaned = {
        k: urllib.parse.unquote_plus(str(v)) if isinstance(v, str) else v
        for k, v in flat_body.items()
    }

    masked_body_str = mask_sensitive_fields(decoded_and_cleaned)

    # Gabungkan semua info ke payload log
    payload_text = f"{method} {url} {masked_body_str}".strip()

    # ✅ Masking inline untuk sesskey/token/secret yang tersembunyi
    payload_text = mask_inline_sensitive_fields(payload_text)

    log_payload = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": "INFO",
        "worker": current_process().name,
        "ip": ip,
        "payload": payload_text
    }

    result = make_prediction(method=method, url=url, body=payload_body, client_ip=ip)

    if result.get("prediction"):
        log_payload.update({
            "prediction": result["prediction"],
            "cache_hit": result.get("cache_hit", False)
        })
        current_app.logger.info(json.dumps(log_payload))
    elif "error" in result:
        log_payload.update({
            "level": "WARN",
            "event": "prediction_failed",
            "error": result["error"]
        })
        current_app.logger.warning(json.dumps(log_payload))
    else:
        log_payload.update({
            "level": "WARN",
            "event": "prediction_skipped_or_empty",
            "reason": "No prediction result returned"
        })
        current_app.logger.warning(json.dumps(log_payload))

def subscribe_to_logs():
    processed_messages = set()
    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('http_logs')
                print("[Subscribe] Subscribed to 'http_logs'")
                last_ping = time.time()

                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    try:
                        raw_message = message['data']
                        message_id = hashlib.sha256(raw_message.encode()).hexdigest()
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        data = json.loads(raw_message)
                        handle_pubsub_message(data)

                    except Exception as e:
                        current_app.logger.error(json.dumps({
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "ERROR",
                            "ip": "N/A",
                            "error": f"Redis message processing error: {str(e)}"
                        }))

                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Redis Connection Error: {e}. Retrying in 5s...")
                time.sleep(5)

def run_flask_app():
    app.run(host="0.0.0.0", port=5000, debug=False)

def spawn_processes():
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()
        print(f"[BOOT] WorkerProcess-{i+1} started")

    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()
    print("[BOOT] SubscriberProcess started")

    flask_proc = Process(target=run_flask_app, name="FlaskProcess")
    flask_proc.daemon = False
    flask_proc.start()
    print("[BOOT] FlaskProcess started")

    try:
        flask_proc.join()
    except KeyboardInterrupt:
        print("\n[Main] KeyboardInterupsi diterima, mematikan...")
        subscriber_proc.terminate()
        for proc in multiprocessing.active_children():
            if proc != flask_proc:
                proc.terminate()
        flask_proc.terminate()

if __name__ == "__main__":
    spawn_processes()