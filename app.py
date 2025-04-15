import threading
import time
import json
from flask import request, jsonify, current_app
from app_factory import create_app
from predict import make_prediction
from rq import Queue
from worker import redis_connection, start_worker
from redis.exceptions import TimeoutError

# Buat aplikasi Flask dan klien Redis
app, redis_client = create_app()

# Buat antrian Redis untuk tugas latar belakang
task_queue = Queue(connection=redis_connection)

# ===================== Rute ===================== #

@app.route("/", methods=["GET"])
def home():
    return "Selamat datang di API Deteksi Intrusi"

@app.route("/favicon.ico")
def favicon():
    return "", 204  # Respon kosong, tidak ada konten

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    input_text = data.get("payload", "").strip()

    if not input_text:
        return jsonify({"error": "Payload diperlukan"}), 400

    # Dapatkan IP klien dan User-Agent dari request
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Tidak Diketahui")

    # Masukkan tugas prediksi ke dalam antrian Redis
    task = task_queue.enqueue(make_prediction, input_text, client_ip, user_agent, job_timeout=None)
    
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    """Periksa status tugas yang ada di antrian."""
    task = task_queue.fetch_job(task_id)
    
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    else:
        return jsonify({"status": "sedang diproses"}), 202

# ===================== Logika Subscription Redis ===================== #

def subscribe_to_logs(app):
    """Berlangganan ke Redis 'moodle_logs' dan memproses setiap pesan."""
    processed_messages = set()  # Lacak pesan yang sudah diproses

    while True:
        try:
            pubsub = redis_connection.pubsub()
            pubsub.subscribe('moodle_logs')
            print(f"Berlangganan ke channel 'moodle_logs' pada thread: {threading.current_thread().name}")

            last_ping = time.time()  # Lacak waktu ping terakhir

            for message in pubsub.listen():
                if message['type'] == 'message':  # Hanya memproses pesan yang sebenarnya
                    try:
                        # Parse pesan yang masuk sebagai JSON
                        data = json.loads(message['data'])

                        # Hindari memproses pesan yang sama beberapa kali
                        message_id = data.get('timestamp')  # Gunakan field timestamp atau ID unik lain
                        if message_id in processed_messages:
                            continue  # Lewati pesan yang sudah diproses

                        # Tandai pesan sebagai diproses
                        processed_messages.add(message_id)

                        print(f"Pesan diterima: {data} pada thread: {threading.current_thread().name}")

                        # Ekstrak field dari pesan
                        payload_obj = data.get('payloadData', {})
                        payload = json.dumps(payload_obj)
                        ip = data.get('ip', 'Tidak Diketahui')

                        # Gunakan konteks aplikasi Flask
                        with app.app_context():
                            current_app.logger.info(f"Memproses payload dari IP {ip}: {payload}")
                            
                            # Panggil fungsi make_prediction dalam konteks app
                            hasil_prediksi = make_prediction(payload, client_ip=ip)

                            # Catat hasil prediksi
                            current_app.logger.info(f"Hasil prediksi: {hasil_prediksi}")

                    except Exception as e:
                        print(f"Kesalahan saat memproses pesan: {str(e)}")
                
                # Kirim PING ke Redis setiap 60 detik untuk menjaga koneksi tetap aktif
                if time.time() - last_ping > 60:
                    redis_connection.ping()
                    last_ping = time.time()

        except TimeoutError:
            print("Redis TimeoutError: Menghubungkan kembali ke Redis...")
            pubsub.close()  # Tutup koneksi saat timeout, lalu ulangi proses

# ===================== Utama ===================== #

if __name__ == "__main__":
    # Jalankan worker Redis dalam background thread
    worker_thread = threading.Thread(target=start_worker)
    worker_thread.daemon = True  # Thread daemon akan berhenti saat program utama keluar
    worker_thread.start()

    # Jalankan subscription Redis dalam background thread lain
    subscriber_thread = threading.Thread(target=subscribe_to_logs, args=(app,))
    subscriber_thread.daemon = True  # Thread daemon akan berhenti saat program utama keluar
    subscriber_thread.start()

    # Jalankan aplikasi Flask
    app.run(host="0.0.0.0", port=5000, debug=False)