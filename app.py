# File: app.py
import os
import json
import time
import redis
import datetime
from flask import Flask, request, jsonify, current_app
from multiprocessing import Process
from rq import Queue
from rq.job import Job
from app_factory import create_app
from predict import make_prediction

# Inisialisasi Flask dan Redis
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

    task = task_queue.enqueue(make_prediction, method, url, body, client_ip, None, job_timeout=None)
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

def subscribe_to_logs():
    app, redis_connection = create_app()
    processed_messages = set()

    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('moodle_logs')
                print(f"[Subscribe] Berlangganan ke 'moodle_logs'")

                last_ping = time.time()

                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    try:
                        data = json.loads(message['data'])
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        user_id = data.get('user_id') or data.get('userid') or 'Tidak Diketahui'
                        payload = data.get('payloadData', {})
                        method = payload.get('method', '')
                        url = payload.get('url', '')
                        body = payload.get('body', '')

                        make_prediction(
                            method=method,
                            url=url,
                            body=body,
                            client_ip=ip,
                            user_id=user_id
                        )

                    except Exception as e:
                        error_ts = datetime.datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
                        current_app.logger.error(json.dumps({
                            "timestamp": error_ts,
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Redis ConnectionError: {e}. Retry 5s...")
                pubsub.close()
                time.sleep(5)

if __name__ == "__main__":
    from worker import start_worker
    from multiprocessing import Process

    # Spawn 3 worker process
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()

    # Spawn subscriber process
    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()

    # Jalankan Flask di proses utama
    app.run(host="0.0.0.0", port=5000, debug=False)