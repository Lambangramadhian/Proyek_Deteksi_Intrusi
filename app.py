import os
import threading
import time
import json
import redis
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
    """Endpoint untuk memproses prediksi."""
    data = request.get_json()
    input_text = data.get("payload", "").strip()
    if not input_text:
        return jsonify({"error": "Payload diperlukan"}), 400 # 400 Bad Request

    # Mendapatkan informasi IP dan User-Agent dari header permintaan
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Tidak Diketahui")
    task = task_queue.enqueue(make_prediction, input_text, client_ip, user_agent, job_timeout=None) 
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
    """Fungsi untuk berlangganan ke Redis PubSub dan memproses pesan."""
    processed_messages = set()
    while True:
        try:
            pubsub = redis_connection.pubsub()
            pubsub.subscribe('moodle_logs')
            print(f"Berlangganan ke channel 'moodle_logs' pada thread: {threading.current_thread().name}")
            last_ping = time.time()

            # Mendengarkan pesan dari Redis PubSub
            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        user_agent = data.get('user_agent', 'Tidak Diketahui')
                        payload_dict = data.get('payloadData', {})
                        input_text = json.dumps(payload_dict)

                        with app.app_context():
                            log_entry = {
                                "timestamp": message_id,
                                "ip": ip,
                                "user_agent": user_agent,
                                "input": payload_dict
                            }
                            current_app.logger.info(f"Memproses: {json.dumps(log_entry)}")
                            hasil_prediksi = make_prediction(input_text, ip, user_agent)
                            current_app.logger.info(json.dumps(hasil_prediksi))
                    except Exception as e:
                        with app.app_context():
                            current_app.logger.error(json.dumps({
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                            }))
                if time.time() - last_ping > 60:
                    redis_connection.ping()
                    last_ping = time.time()
        except TimeoutError:
            print("Redis TimeoutError: Menghubungkan kembali ke Redis...")
            pubsub.close()
            continue

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