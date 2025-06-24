# ====================
# Library Internal (modul-modul buatan sendiri dalam proyek ini)
# ====================
import json                                            # Untuk parsing dan pembuatan objek JSON
import time                                            # Untuk fungsi-fungsi berbasis waktu (misalnya timestamp)
import redis                                           # Untuk koneksi dengan Redis (digunakan oleh antrean RQ)
import urllib.parse                                    # Untuk memproses dan memanipulasi URL
import datetime                                        # Untuk menangani tanggal dan waktu
import multiprocessing                                 # Untuk menjalankan proses paralel
import hashlib                                         # Untuk hashing pesan (digunakan dalam Pub/Sub)

from flask import request, jsonify, current_app        # Flask core - menangani permintaan HTTP dan respons JSON
from multiprocessing import Process, current_process   # Untuk memproses tugas secara paralel
from rq import Queue                                   # Redis Queue - untuk sistem antrean background job
from rq.job import Job                                 # Untuk manajemen job pada antrean

# ====================
# Library Eksternal / Buatan Sendiri (Modul Khusus Proyek)
# ====================
from app_factory import create_app                     # Factory function untuk membuat instance Flask app
from predict import make_prediction                    # Fungsi utama untuk melakukan prediksi
from worker import start_worker                        # Fungsi untuk memulai worker Redis (background job handler)
from utils import (                                    # Utilitas tambahan untuk pre-processing dan keamanan data
    flatten_dict,                                      # Flatten struktur data nested
    parse_payload,                                     # Parsing payload dari request
    mask_sensitive_fields,                             # Menyembunyikan data sensitif dalam payload
    mask_url_query,                                    # Menyembunyikan query parameter sensitif dalam URL
    mask_inline_sensitive_fields                       # Menyembunyikan data sensitif inline (misal dalam string JSON)
)


# Inisialisasi aplikasi Flask dan koneksi Redis
app, redis_connection = create_app()
task_queue = Queue(connection=redis_connection)

# Setup logging
@app.route("/", methods=["GET"])
def home():
    """Endpoint utama untuk API."""
    return "Selamat datang di API Deteksi Intrusi"

# Route untuk favicon.ico agar tidak mengganggu log
@app.route("/favicon.ico")
def favicon():
    """Endpoint untuk favicon.ico agar tidak mengganggu log."""
    return "", 204

# Endpoint untuk menerima permintaan prediksi
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

# Endpoint untuk memeriksa status tugas
@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    """Endpoint untuk memeriksa status tugas prediksi."""
    task: Job = task_queue.fetch_job(task_id)
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202

def handle_pubsub_message(data):
    """Fungsi untuk menangani pesan dari Redis Pub/Sub."""
    ip = data.get("ip_address") or data.get("ip") or "Tidak Diketahui"
    method = data.get("method", "").upper()
    url = urllib.parse.unquote(data.get("url", ""))
    url = mask_url_query(url)

    # Ambil payload dari data
    raw_payload = data.get("payloadData") or data.get("payload")
    payload_body = parse_payload(raw_payload, url=url, ip=ip, logger=current_app.logger)

    # Jika body berupa string, coba decode
    flat_body = flatten_dict(payload_body)
    flat_body.pop("raw", None)

    # Decode nilai-nilai dalam flat_body
    decoded_and_cleaned = {
        k: urllib.parse.unquote_plus(str(v)) if isinstance(v, str) else v
        for k, v in flat_body.items()
    }

    # Masking field sensitif
    masked_body_str = mask_sensitive_fields(decoded_and_cleaned)

    # Gabungkan semua info ke payload log
    payload_text = f"{method} {url} {masked_body_str}".strip()

    # ✅ Masking inline untuk sesskey/token/secret yang tersembunyi
    payload_text = mask_inline_sensitive_fields(payload_text)

    # Buat payload log
    log_payload = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": "INFO",
        "worker": current_process().name,
        "ip": ip,
        "payload": payload_text
    }

    # Log payload awal
    result = make_prediction(method=method, url=url, body=payload_body, client_ip=ip)

    # Tambahkan informasi prediksi ke log_payload
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
    """Fungsi untuk berlangganan ke Redis Pub/Sub dan memproses pesan yang diterima."""
    processed_messages = set()
    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('http_logs')
                print("[Subscribe] Subscribed to 'http_logs'")
                last_ping = time.time()

                # Mulai mendengarkan pesan dari Redis Pub/Sub
                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    try:
                        raw_message = message['data']
                        message_id = hashlib.sha256(raw_message.encode()).hexdigest()
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        # Decode pesan JSON
                        data = json.loads(raw_message)
                        handle_pubsub_message(data)

                    # Jika terjadi kesalahan saat memproses pesan
                    except Exception as e:
                        current_app.logger.error(json.dumps({
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "ERROR",
                            "ip": "N/A",
                            "error": f"Redis message processing error: {str(e)}"
                        }))

                    # Cek koneksi Redis setiap 60 detik
                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            # Jika terjadi kesalahan koneksi Redis
            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Redis Connection Error: {e}. Retrying in 5s...")
                time.sleep(5)

def run_flask_app():
    """Fungsi untuk menjalankan aplikasi Flask."""
    app.run(host="0.0.0.0", port=5000, debug=False)

def spawn_processes():
    """Fungsi untuk memulai semua proses yang diperlukan."""
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()
        print(f"[BOOT] WorkerProcess-{i+1} dimulai")

    # Tunggu beberapa detik untuk memastikan worker sudah siap
    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()
    print("[BOOT] SubscriberProcess dimulai")

    # Tunggu beberapa detik untuk memastikan subscriber sudah siap
    flask_proc = Process(target=run_flask_app, name="FlaskProcess")
    flask_proc.daemon = False
    flask_proc.start()
    print("[BOOT] FlaskProcess dimulai")

    # Tunggu proses Flask selesai
    try:
        flask_proc.join()
    except KeyboardInterrupt:
        print("\n[Main] KeyboardInterupsi diterima, mematikan...")
        subscriber_proc.terminate()
        for proc in multiprocessing.active_children():
            if proc != flask_proc:
                proc.terminate()
        flask_proc.terminate()

# Main entry point
if __name__ == "__main__":
    spawn_processes()