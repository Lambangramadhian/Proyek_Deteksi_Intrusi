# Import library standar dan eksternal
import json
import time
import redis
import datetime
import urllib.parse
from flask import request, jsonify, current_app
from multiprocessing import Process
from rq import Queue
from rq.job import Job
from multiprocessing import current_process

# Import dari modul internal
from app_factory import create_app
from predict import make_prediction
from worker import start_worker

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

def subscribe_to_logs():
    """Berlangganan ke Redis channel 'http_logs', parsing log, prediksi dan logging hasilnya."""
    app, redis_connection = create_app()
    processed_messages = set()

    # Pastikan Redis terhubung
    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('http_logs')
                print("[Subscribe] Berlangganan ke 'http_logs'")
                last_ping = time.time()

                # Mulai mendengarkan pesan dari Redis
                for message in pubsub.listen():
                    if message['type'] != 'message':
                        continue

                    # Cek apakah pesan sudah diproses sebelumnya
                    try:
                        data = json.loads(message['data'])
                        message_id = data.get('timestamp')
                        if message_id in processed_messages:
                            continue
                        processed_messages.add(message_id)

                        # Ambil informasi dari pesan
                        ip = data.get('ip_address') or data.get('ip') or 'Tidak Diketahui'
                        method = data.get("method", "").upper()
                        url = urllib.parse.unquote(data.get("url", ""))
                        status_code = data.get("status_code")

                        # Ambil payload
                        raw_payload = data.get("payloadData") or data.get("payload")
                        payload_body = {}

                        # Cek apakah payload berupa string atau dictionary
                        if isinstance(raw_payload, str):
                            try:
                                parsed = json.loads(raw_payload)
                                if isinstance(parsed, list) and len(parsed) > 0:
                                    full_body = dict(parsed[0])
                                    args = full_body.pop("args", {})
                                    full_body.update(args)
                                    payload_body = full_body
                                elif isinstance(parsed, dict):
                                    payload_body = parsed
                                else:
                                    payload_body = {"raw": str(parsed)}
                            except json.JSONDecodeError:
                                payload_body = {"raw": raw_payload}
                        elif isinstance(raw_payload, dict):
                            payload_body = raw_payload
                        else:
                            payload_body = {"raw": str(raw_payload)}

                        # Flatten dictionary rekursif
                        def flatten_dict(d, parent_key='', sep='||'):
                            items = []
                            for k, v in d.items():
                                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                                if isinstance(v, dict):
                                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                                else:
                                    items.append((new_key, v))
                            return dict(items)

                        # Flatten payload body untuk logging
                        flat_body = flatten_dict(payload_body)
                        flat_body.pop("raw", None)  # hindari duplikasi jika sudah parse

                        # Tambahan parse raw form-urlencoded (logintoken=...&password=...)
                        raw_value = payload_body.get("raw")
                        if isinstance(raw_value, str) and "=" in raw_value:
                            try:
                                parsed_raw = dict(urllib.parse.parse_qsl(raw_value))
                                flat_body.update(parsed_raw)
                            except Exception:
                                pass

                        # Masking untuk key sensitif
                        sensitive_keys = ["password", "token", "auth", "key"]
                        masked_body_str = " ".join(
                            f"{k}=*****" if any(s in k.lower() for s in sensitive_keys) else f"{k}={v}"
                            for k, v in flat_body.items()
                        )

                        # Struktur log
                        log_payload = {
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "INFO",
                            "worker": current_process().name,
                            "ip": ip,
                            "payload": f"{url} {masked_body_str}".strip()
                        }

                        # Lakukan prediksi
                        result = make_prediction(
                            method=method,
                            url=url,
                            body=payload_body,
                            client_ip=ip,
                            status_code=status_code
                        )

                        # Tambahkan hasil prediksi ke log jika ada
                        if result.get("prediction") and current_process().name != "SubscriberProcess":
                            log_payload.update({
                                "prediction": result["prediction"],
                                "cache_hit": result.get("cache_hit", False)
                            })
                            current_app.logger.info(json.dumps(log_payload))

                    # Jika terjadi kesalahan saat memproses pesan Redis
                    except Exception as e:
                        current_app.logger.error(json.dumps({
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "ERROR",
                            "ip": "N/A",
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    # Pastikan Redis tetap terhubung dengan melakukan ping setiap 60 detik
                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            # Tangani kesalahan koneksi Redis
            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Redis Connection Error: {e}. Retry dalam 5 detik...")
                time.sleep(5)

# Entry point utama saat aplikasi dijalankan
if __name__ == "__main__":

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
