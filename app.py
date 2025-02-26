from flask import request, jsonify
from app_factory import create_app
from predict import make_prediction
from rq import Queue
from worker import redis_connection

# Buat aplikasi dan Redis client
app, redis_client = create_app()

# Buat Redis queue untuk tugas latar belakang
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
    input_text = data.get("payload", "").strip()  # Ambil payload dari permintaan

    if not input_text:
        return jsonify({"error": "Payload diperlukan"}), 400

    # Dapatkan IP client dan User-Agent dari permintaan
    client_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent", "Tidak Dikenal")

    # Lepaskan tugas prediksi ke Redis Queue (kirim input_text, client_ip, user_agent)
    task = task_queue.enqueue(make_prediction, input_text, client_ip, user_agent, job_timeout=None)  # Nonaktifkan timeout
    
    return jsonify({"task_id": task.id, "message": "Tugas prediksi dimulai"}), 202

@app.route("/task-status/<task_id>", methods=["GET"])
def task_status(task_id):
    """Periksa status dari tugas yang ada di antrian."""
    task = task_queue.fetch_job(task_id)
    
    if task is None:
        return jsonify({"error": "Tugas tidak ditemukan"}), 404
    
    if task.is_finished:
        return jsonify({"status": "selesai", "hasil": task.result}), 200
    elif task.is_failed:
        return jsonify({"status": "gagal", "error": str(task.exc_info)}), 500
    else:
        return jsonify({"status": "sedang diproses"}), 202

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)