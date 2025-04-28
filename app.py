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
from redis.exceptions import TimeoutError

# Koneksi Redis dinamis berdasarkan env
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_connection = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

# Inisialisasi Flask dan Redis client
app, _ = create_app()
task_queue = Queue(connection=redis_connection)

# Inisialisasi logger
@app.route("/", methods=["GET"])
def home():
    """Halaman utama aplikasi."""
    return "Selamat datang di API Deteksi Intrusi" # Mengembalikan pesan sambutan

# Endpoint untuk favicon
@app.route("/favicon.ico")
def favicon():
    """Mengembalikan favicon kosong."""
    return "", 204 # Mengembalikan status 204 No Content

# Endpoint untuk memproses prediksi
@app.route("/predict", methods=["POST"])
def predict():
    """Endpoint untuk memproses prediksi berdasarkan payload yang diterima."""
    data = request.get_json()
    payload = data.get("payload", {})
    method = payload.get("method", "")
    url = payload.get("url", "")
    body = payload.get("body", "")
    client_ip = request.remote_addr

    # Validasi input
    if not method or not url:
        return jsonify({"error": "Method dan URL diperlukan"}), 400 # 400 Bad Request

    # Menggunakan RQ untuk memproses prediksi secara asinkron
    task = task_queue.enqueue(make_prediction, method, url, body, client_ip, job_timeout=None)
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202 # 202 Accepted

# Mendapatkan status tugas berdasarkan task_id
@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    """Endpoint untuk mendapatkan status tugas berdasarkan task_id."""
    task: Job = task_queue.fetch_job(task_id)
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202

def subscribe_to_logs(app):
    """Subscribe ke Redis channel dan proses payload."""
    processed_messages = set()

    while True:
        try:
            pubsub = redis_connection.pubsub()
            pubsub.subscribe('moodle_logs')
            print(f"[Subscribe] Berlangganan ke 'moodle_logs' pada thread: {threading.current_thread().name}")

            last_ping = time.time()

            for message in pubsub.listen():
                if message['type'] == 'message':
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
                            # Rapi format log payload
                            readable_json = json.dumps({
                                "method": method,
                                "url": url,
                                "body": body
                            }, indent=4, ensure_ascii=False)

                            # Log input satu kali saja
                            current_app.logger.info(f"[{message_id}] IP: {ip} | User-ID: {user_id} | Input: {readable_json}")

                            # Panggil prediksi
                            hasil_prediksi = make_prediction(
                                method=method,
                                url=url,
                                body=body,
                                client_ip=ip,
                                user_id=user_id
                            )

                    except Exception as e:
                        with app.app_context():
                            current_app.logger.error(json.dumps({
                                "timestamp": datetime.datetime.now().isoformat(),
                                "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                            }))

                if time.time() - last_ping > 60:
                    redis_connection.ping()
                    last_ping = time.time()

        except redis.exceptions.ConnectionError as e:
            print(f"[Subscribe] Redis ConnectionError: {e}. Retry 5s...")
            pubsub.close()
            time.sleep(5)

# Menjalankan worker RQ di thread terpisah
if __name__ == "__main__":
    from worker import start_worker
    worker_thread = threading.Thread(target=start_worker, daemon=True)
    worker_thread.start()

    # Menjalankan thread untuk berlangganan ke Redis PubSub
    subscriber_thread = threading.Thread(target=subscribe_to_logs, args=(app,), daemon=True)
    subscriber_thread.start()

    # Menjalankan aplikasi Flask
    app.run(host="0.0.0.0", port=5000, debug=False)