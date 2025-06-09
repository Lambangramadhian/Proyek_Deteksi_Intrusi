# Import library standar dan eksternal
import json
import time
import redis
import datetime
import urllib.parse
import multiprocessing
from flask import request, jsonify, current_app
from multiprocessing import Process, current_process
from rq import Queue
from rq.job import Job

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
    current_app.logger.info(f"Enqueued task: {task.id}")

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

    with app.app_context():
        while True:
            try:
                pubsub = redis_connection.pubsub()
                pubsub.subscribe('http_logs')
                print("[Subscribe] Berlangganan ke 'http_logs'")
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
                        method = data.get("method", "").upper()
                        url = urllib.parse.unquote(data.get("url", ""))
                        status_code = data.get("status_code")

                        raw_payload = data.get("payloadData") or data.get("payload")
                        payload_body = {}

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

                        def flatten_dict(d, parent_key='', sep='||'):
                            items = []
                            for k, v in d.items():
                                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                                if isinstance(v, dict):
                                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                                else:
                                    items.append((new_key, v))
                            return dict(items)

                        flat_body = flatten_dict(payload_body)
                        flat_body.pop("raw", None)  # Hindari duplikasi jika sudah parse

                        # ✅ Decode raw form-urlencoded payload
                        raw_value = payload_body.get("raw")
                        # Decode + parse raw payload, lalu update flat_body
                        if isinstance(raw_value, str):
                            decoded_raw = urllib.parse.unquote_plus(raw_value)
                            if "=" in decoded_raw:
                                try:
                                    parsed_raw = dict(urllib.parse.parse_qsl(decoded_raw))
                                    flat_body.update(parsed_raw)
                                except Exception:
                                    pass

                            if "=" in decoded_raw:
                                try:
                                    parsed_raw = dict(urllib.parse.parse_qsl(decoded_raw))
                                    flat_body.update(parsed_raw)
                                except Exception:
                                    pass

                        # ✅ Masking untuk key sensitif
                        sensitive_keys = ["password", "token", "auth", "key"]
                        masked_body_str = " ".join(
                            f"{k}=*****" if any(s in k.lower() for s in sensitive_keys) else f"{k}={v}"
                            for k, v in flat_body.items()
                        )

                        log_payload = {
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "INFO",
                            "worker": current_process().name,
                            "ip": ip,
                            "payload": f"{method} {url} {masked_body_str}".strip()
                        }

                        result = make_prediction(
                            method=method,
                            url=url,
                            body=payload_body,
                            client_ip=ip,
                            status_code=status_code
                        )

                        if result.get("prediction"):
                            log_payload.update({
                                "prediction": result["prediction"],
                                "cache_hit": result.get("cache_hit", False)
                            })
                            current_app.logger.info(json.dumps(log_payload))

                    except Exception as e:
                        current_app.logger.error(json.dumps({
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "level": "ERROR",
                            "ip": "N/A",
                            "error": f"Kesalahan saat memproses pesan Redis: {str(e)}"
                        }))

                    if time.time() - last_ping > 60:
                        redis_connection.ping()
                        last_ping = time.time()

            except redis.exceptions.ConnectionError as e:
                print(f"[Subscribe] Redis Connection Error: {e}. Retry dalam 5 detik...")
                time.sleep(5)

def run_flask_app():
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
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

    # Menunggu proses Flask selesai
    try:
        flask_proc.join()
    except KeyboardInterrupt:
        print("\n[Main] KeyboardInterrupt diterima, menghentikan proses...")
        subscriber_proc.terminate()
        for proc in multiprocessing.active_children():
            if proc != flask_proc:
                proc.terminate()
        flask_proc.terminate()
