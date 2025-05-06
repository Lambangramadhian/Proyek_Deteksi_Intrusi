import os
import json
import redis
import joblib
import hashlib
import datetime
import multiprocessing
import threading
from flask import current_app

# Buat direktori untuk menyimpan model jika belum ada
model_dir = 'model'
os.makedirs(model_dir, exist_ok=True)

# Path default untuk model dan vectorizer
model_path = os.getenv("MODEL_PATH", os.path.join(model_dir, "random_forest_web_ids.pkl"))
vectorizer_path = os.getenv("VECTORIZER_PATH", os.path.join(model_dir, "tfidf_vectorizer.pkl"))

# Load model dan vectorizer
model = joblib.load(model_path)
vectorizer = joblib.load(vectorizer_path)

# Inisialisasi koneksi Redis
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# Cache untuk nama worker unik per PID
_worker_name_cache = {}
_worker_lock = threading.Lock()

def get_worker_name() -> str:
    """Menghasilkan nama worker yang konsisten berdasarkan PID (Process ID)."""
    pid = multiprocessing.current_process().pid
    with _worker_lock:
        if pid not in _worker_name_cache:
            index = len(_worker_name_cache) + 1
            _worker_name_cache[pid] = f"WorkerProcess-{index}"
        return _worker_name_cache[pid]

def get_cache_key(input_text: str) -> str:
    """Menghasilkan kunci cache unik berdasarkan teks input."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def flatten_dict(d, parent_key='', sep='||'):
    """Mengubah dictionary bersarang menjadi datar (flatten) dengan pemisah khusus."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            # Rekursif untuk dictionary bersarang
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def make_prediction(method: str, url: str, body, client_ip: str = "Tidak Diketahui", user_id: str = "Tidak Diketahui") -> dict:
    """Fungsi utama untuk membuat prediksi berdasarkan data request."""
    try:
        now = datetime.datetime.now()
        timestamp_str = now.strftime("[%d/%m/%Y %H:%M:%S]")
        process_name = get_worker_name()

        # Menangani body dalam bentuk dictionary atau string
        if isinstance(body, dict):
            flat_body = flatten_dict(body)
            body_string = " ".join(f"{k}={v}" for k, v in flat_body.items())
        elif isinstance(body, str):
            body_string = body.strip()
        else:
            body_string = ""

        # Gabungkan semua input untuk vektorisasi
        input_text = f"{method.strip()} {url.strip()} {body_string}".strip()

        # Menyiapkan log input dalam format terstruktur
        structured_log = {
            "method": method,
            "url": url,
            "body": body
        }
        formatted_input = json.dumps(structured_log, indent=4, ensure_ascii=False)

        # Logging input ke sistem log
        current_app.logger.info(
            f"{timestamp_str} Worker: {process_name} | IP: {client_ip} | User-ID: {user_id} | Input: {formatted_input}"
        )

        # Validasi bahwa input tidak kosong
        if not input_text:
            return {"error": "Payload diperlukan"}

        # Cek apakah hasil prediksi sudah ada di cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"{timestamp_str} Worker: {process_name} | Prediksi (cache): {hasil_cache}")
            return {"prediction": hasil_cache}

        # Lakukan vektorisasi dan prediksi menggunakan model
        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]

        # Konversi hasil prediksi menjadi label yang mudah dipahami
        label_map = {0: "Normal", 1: "SQL Injection", 2: "XSS"}
        label = label_map.get(pred, "Tidak Diketahui")

        # Simpan hasil prediksi ke cache dengan masa berlaku 60 detik
        redis_client.setex(cache_key, 60, label)

        # Logging hasil prediksi
        current_app.logger.info(f"{timestamp_str} Worker: {process_name} | Prediksi: {label}")
        return {"prediction": label}

    # Handle kesalahan yang mungkin terjadi selama proses prediksi
    except Exception as e:
        # Logging kesalahan yang terjadi saat proses prediksi
        error_ts = datetime.datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
        current_app.logger.error(json.dumps({
            "timestamp": error_ts,
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}