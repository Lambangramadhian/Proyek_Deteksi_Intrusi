# Import library bawaan dan eksternal yang dibutuhkan
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

# Inisialisasi aplikasi Flask dan koneksi Redis melalui fungsi factory
app, redis_connection = create_app()

# Membuat antrean Redis Queue untuk eksekusi background task
task_queue = Queue(connection=redis_connection)

# Endpoint utama (root) hanya untuk pengecekan awal service
@app.route("/", methods=["GET"])
def home():
    return "Selamat datang di API Deteksi Intrusi"

# Endpoint favicon agar tidak menghasilkan error di browser
@app.route("/favicon.ico")
def favicon():
    return "", 204

# Endpoint POST untuk menerima input payload dan mengirimnya ke antrean prediksi
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()  # Mengambil data dari body permintaan
    payload = data.get("payload", {})  # Mengambil isi dari key 'payload'
    method = payload.get("method", "")  # Ekstrak method HTTP dari payload
    url = payload.get("url", "")        # Ekstrak URL dari payload
    body = payload.get("body", "")      # Ekstrak body dari payload
    client_ip = request.remote_addr     # Mendapatkan alamat IP dari klien

    # Validasi wajib: method dan URL tidak boleh kosong
    if not method or not url:
        return jsonify({"error": "Method dan URL diperlukan"}), 400

    # Menambahkan tugas ke Redis Queue agar diproses di background
    task = task_queue.enqueue(
        make_prediction, method, url, body, client_ip, None, job_timeout=None
    )

    # Mengembalikan ID task agar klien bisa cek status nanti
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

# Endpoint untuk mengecek status dari task prediksi berdasarkan task_id
@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    task: Job = task_queue.fetch_job(task_id)  # Mengambil job dari Redis Queue
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202  # Jika belum selesai

# Fungsi subscriber untuk mendengarkan channel Redis dan memproses payload dari sana
def subscribe_to_logs():
    app, redis_connection = create_app()
    processed_messages = set()  # Untuk menghindari duplikasi proses pesan

    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('moodle_logs')  # Subskripsi ke channel 'moodle_logs'
                print(f"[Subscribe] Berlangganan ke 'moodle_logs'")

                last_ping = time.time()

                for message in pubsub.listen():  # Mendengarkan pesan masuk
                    if message['type'] != 'message':
                        continue

                    try:
                        data = json.loads(message['data'])  # Parsing data JSON
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue  # Lewati jika sudah diproses
                        processed_messages.add(message_id)

                        # Ambil info IP, user ID, dan payload (method, url, body)
                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        user_id = data.get('user_id') or data.get('userid') or 'Tidak Diketahui'
                        payload = data.get('payloadData', {})
                        method = payload.get('method', '')
                        url = payload.get('url', '')
                        body = payload.get('body', '')

                        # Logging input dari Redis
                        log_payload = {
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "INFO",
                            "source": "RedisSubscriber",
                            "ip": ip,
                            "user_id": user_id,
                            "payload": f"{method} {url} {body}".strip()
                        }
                        current_app.logger.info(json.dumps(log_payload))

                        # Langsung jalankan prediksi (sinkron)
                        make_prediction(
                            method=method,
                            url=url,
                            body=body,
                            client_ip=ip,
                            user_id=user_id
                        )

                    except Exception as e:
                        # Logging error jika terjadi kegagalan parsing/prediksi
                        error_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        current_app.logger.error(json.dumps({
                            "timestamp": error_ts,
                            "level": "ERROR",
                            "source": "RedisSubscriber",
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    # Ping Redis setiap 60 detik untuk menjaga koneksi tetap aktif
                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Kesalahan Koneksi Redis: {e}. Mencoba ulang dalam 5 detik...")
                time.sleep(5)

# Entry point utama ketika file dijalankan langsung
if __name__ == "__main__":
    from worker import start_worker

    # Jalankan 3 worker RQ secara paralel
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()

    # Jalankan proses subscriber untuk mendengarkan Redis
    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()

    # Jalankan server Flask
    app.run(host="0.0.0.0", port=5000, debug=False)