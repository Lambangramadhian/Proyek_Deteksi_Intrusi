import os
import threading
import time
import json
import redis
import datetime
from flask import request, jsonify, current_app
from app_factory import create_app
from predict import make_prediction
from rq import Queue
from rq.job import Job

# Koneksi Redis dinamis
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_connection = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

# Inisialisasi Flask dan RQ
app, _ = create_app()
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


def subscribe_to_logs(app):
    processed_messages = set()

    while True:
        pubsub = redis_connection.pubsub()
        try:
            pubsub.subscribe('moodle_logs')
            print(f"[Subscribe] Berlangganan ke 'moodle_logs' pada thread: {threading.current_thread().name}")

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

                    with app.app_context():
                        make_prediction(
                            method=method,
                            url=url,
                            body=body,
                            client_ip=ip,
                            user_id=user_id
                        )

                except Exception as e:
                    with app.app_context():
                        error_ts = datetime.datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
                        current_app.logger.error(json.dumps({
                            "timestamp": error_ts,
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                if time.time() - last_ping > 60:
                    try:
                        redis_connection.ping()
                        last_ping = time.time()
                    except redis.exceptions.ConnectionError as ping_err:
                        print(f"[Subscribe] Redis ping gagal: {ping_err}")
                        break  # keluar dari for loop, kembali ke while True (reconnect)

        except redis.exceptions.TimeoutError as timeout_err:
            print(f"[Subscribe] Redis TimeoutError: {timeout_err}. Mencoba kembali dalam 5 detik...")
            time.sleep(5)

        except redis.exceptions.ConnectionError as conn_err:
            print(f"[Subscribe] Redis ConnectionError: {conn_err}. Mencoba kembali dalam 5 detik...")
            time.sleep(5)

        finally:
            pubsub.close()



if __name__ == "__main__":
    from worker import start_worker
    worker_thread = threading.Thread(target=start_worker, daemon=True)
    worker_thread.start()

    subscriber_thread = threading.Thread(target=subscribe_to_logs, args=(app,), daemon=True)
    subscriber_thread.start()

    app.run(host="0.0.0.0", port=5000, debug=False)