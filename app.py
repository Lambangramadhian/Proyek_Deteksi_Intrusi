# Import library standar dan eksternal
import json
import time
import redis
import datetime
from flask import Flask, request, jsonify, current_app
from multiprocessing import Process
from rq import Queue
from rq.job import Job
from multiprocessing import current_process

# Import dari modul internal
from app_factory import create_app
from predict import make_prediction

# Inisialisasi aplikasi Flask dan koneksi Redis
app, redis_connection = create_app()

# Membuat antrean Redis Queue untuk task asynchronous
task_queue = Queue(connection=redis_connection)

# Endpoint GET root sebagai penanda bahwa API aktif
@app.route("/", methods=["GET"])
def home():
    return "Selamat datang di API Deteksi Intrusi"

# Endpoint favicon agar tidak menghasilkan error saat diakses oleh browser
@app.route("/favicon.ico")
def favicon():
    return "", 204

# Endpoint utama untuk menerima permintaan prediksi
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()                        # Ambil data JSON dari request body
    payload = data.get("payload", {})                # Ambil bagian payload
    method = payload.get("method", "")               # Ambil method HTTP (misalnya GET, POST)
    url = payload.get("url", "")                     # Ambil URL target
    body = payload.get("body", "")                   # Ambil body permintaan
    client_ip = request.remote_addr                  # Ambil IP klien dari permintaan

    # Validasi: method dan url harus disediakan
    if not method or not url:
        return jsonify({"error": "Method dan URL diperlukan"}), 400

    # Masukkan tugas ke antrean untuk diproses secara asynchronous
    task = task_queue.enqueue(
        make_prediction, method, url, body, client_ip, None, job_timeout=None
    )

    # Kembalikan ID task sebagai response
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

# Endpoint untuk mengecek status dari sebuah task berdasarkan ID
@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    task: Job = task_queue.fetch_job(task_id)        # Ambil job berdasarkan ID
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202

# Fungsi subscriber untuk mendengarkan log dari Redis
def subscribe_to_logs():
    """Berlangganan ke Redis dan log payload secara terstruktur tanpa field 'source'."""
    app, redis_connection = create_app()
    processed_messages = set()  # Simpan ID pesan yang sudah diproses

    # Inisialisasi Redis PubSub
    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('moodle_logs')  # Subskripsi ke channel Redis
                print(f"[Subscribe] Berlangganan ke 'moodle_logs'")
                last_ping = time.time()

                # Loop untuk mendengarkan setiap pesan baru dari channel Redis
                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue

                    # Cek apakah pesan sudah diproses sebelumnya
                    try:
                        data = json.loads(message['data'])  # Parse JSON
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue  # Lewati jika sudah diproses
                        processed_messages.add(message_id)

                        # Ambil informasi penting dari payload
                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        user_id = data.get('user_id') or data.get('userid') or 'Tidak Diketahui'
                        payload = data.get('payloadData', {})
                        method = payload.get('method', '')
                        url = payload.get('url', '')
                        body = payload.get('body', '')

                        # Konversi body ke string jika berbentuk dictionary
                        body_str = body if isinstance(body, str) else " ".join(
                            f"{k}={v}" for k, v in body.items()
                        )

                        # Buat log terstruktur
                        worker_log_payload = {
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "INFO",
                            "worker": current_process().name,
                            "ip": ip,
                            "user_id": user_id,
                            "payload": f"{method} {url} {body_str}".strip()
                        }

                        # Langsung jalankan prediksi
                        result = make_prediction(
                            method=method,
                            url=url,
                            body=body,
                            client_ip=ip,
                            user_id=user_id
                        )

                        # Jika ada hasil prediksi, log ke file
                        if result.get("prediction"):
                            worker_log_payload.update({
                                "prediction": result["prediction"],
                                "cache_hit": result.get("cache_hit", False)
                            })
                            current_app.logger.info(json.dumps(worker_log_payload))

                    # Log jika tidak ada payload yang ditemukan
                    except Exception as e:
                        # Logging jika terjadi error saat parsing atau prediksi
                        error_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        current_app.logger.error(json.dumps({
                            "timestamp": error_ts,
                            "level": "ERROR",
                            "ip": "N/A",
                            "user_id": "N/A",
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    # Ping Redis setiap 60 detik agar koneksi tidak timeout
                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            # Tangani kesalahan koneksi Redis
            except redis.exceptions.ConnectionError as e:
                # Retry jika koneksi Redis terputus
                print(f"[Subscribe] Redis Connection Error: {e}. Retry dalam 5 detik...")
                time.sleep(5)

# Entry point utama saat aplikasi dijalankan
if __name__ == "__main__":
    from worker import start_worker

    # Jalankan 3 proses worker untuk menangani task dari antrean
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()

    # Jalankan proses subscriber Redis untuk monitoring log
    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()

    # Jalankan aplikasi Flask di host 0.0.0.0 pada port 5000
    app.run(host="0.0.0.0", port=5000, debug=False)
