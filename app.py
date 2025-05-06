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

# Endpoint root ("/") untuk menampilkan pesan selamat datang
@app.route("/", methods=["GET"])
def home():
    return "Selamat datang di API Deteksi Intrusi"

# Endpoint untuk favicon (biasanya diminta browser secara otomatis), dikembalikan kosong (status 204: No Content)
@app.route("/favicon.ico")
def favicon():
    return "", 204

# Endpoint POST "/predict" untuk menerima data dan memproses prediksi deteksi intrusi secara asynchronous
@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()  # Mengambil data JSON dari permintaan
    payload = data.get("payload", {})  # Mengambil bagian "payload" dari JSON
    method = payload.get("method", "")  # Metode HTTP yang akan dianalisis
    url = payload.get("url", "")        # URL target yang akan dianalisis
    body = payload.get("body", "")      # Isi permintaan HTTP
    client_ip = request.remote_addr     # Alamat IP dari klien yang mengirim permintaan

    # Validasi: method dan url harus ada
    if not method or not url:
        return jsonify({"error": "Method dan URL diperlukan"}), 400

    # Menambahkan tugas prediksi ke antrean (queue) menggunakan RQ
    # Fungsi make_prediction dijalankan secara asynchronous
    task = task_queue.enqueue(make_prediction, method, url, body, client_ip, None, job_timeout=None)

    # Mengembalikan ID tugas agar bisa dicek statusnya nanti
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

# Endpoint untuk mengecek status tugas prediksi berdasarkan task_id
@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    task: Job = task_queue.fetch_job(task_id)  # Mengambil job dari antrean berdasarkan ID
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    return jsonify({"status": "sedang diproses"}), 202  # Default: tugas masih berjalan

def subscribe_to_logs():
    """Fungsi untuk berlangganan ke Redis dan memproses pesan yang diterima."""
    app, redis_connection = create_app()
    processed_messages = set()

    # Inisialisasi koneksi Redis
    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('moodle_logs')
                print(f"[Subscribe] Berlangganan ke 'moodle_logs'")

                # Mengatur waktu ping terakhir
                last_ping = time.time()

                # Perulangan untuk mendengarkan pesan dari Redis
                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue
                    try:
                        data = json.loads(message['data'])
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        # Mengambil data dari pesan Redis
                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        user_id = data.get('user_id') or data.get('userid') or 'Tidak Diketahui'
                        payload = data.get('payloadData', {})
                        method = payload.get('method', '')
                        url = payload.get('url', '')
                        body = payload.get('body', '')

                        # Memanggil fungsi prediksi
                        make_prediction(
                            method=method,
                            url=url,
                            body=body,
                            client_ip=ip,
                            user_id=user_id
                        )

                    # Penanganan kesalahan saat mendekode JSON
                    except Exception as e:
                        error_ts = datetime.datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
                        current_app.logger.error(json.dumps({
                            "timestamp": error_ts,
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    # Memeriksa apakah koneksi Redis masih aktif
                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            # Penanganan kesalahan koneksi Redis
            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Kesalahan Koneksi Redis: {e}. Mencoba ulang dalam 5 detik...")
                pubsub.close()
                time.sleep(5)

# Fungsi utama untuk menjalankan aplikasi Flask dan worker RQ
if __name__ == "__main__":
    from worker import start_worker
    from multiprocessing import Process

    # Menjalankan 3 proses worker
    for i in range(3):
        p = Process(target=start_worker, name=f"WorkerProcess-{i+1}")
        p.daemon = True
        p.start()

    # Menjalankan proses subscriber
    subscriber_proc = Process(target=subscribe_to_logs, name="SubscriberProcess")
    subscriber_proc.daemon = True
    subscriber_proc.start()

    # Menjalankan aplikasi Flask di proses utama
    app.run(host="0.0.0.0", port=5000, debug=False)