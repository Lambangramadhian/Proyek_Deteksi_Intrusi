# Import library standar dan eksternal
import os
import json
import redis
import joblib
import hashlib
import datetime
import multiprocessing
import threading
from flask import current_app

# Buat direktori model jika belum ada
model_dir = 'model'
os.makedirs(model_dir, exist_ok=True)

# Path default untuk model dan vectorizer, bisa dioverride lewat environment variable
model_path = os.getenv("MODEL_PATH", os.path.join(model_dir, "random_forest_web_ids.pkl"))
vectorizer_path = os.getenv("VECTORIZER_PATH", os.path.join(model_dir, "tfidf_vectorizer.pkl"))

# Load model dan vectorizer dari file
model = joblib.load(model_path)
vectorizer = joblib.load(vectorizer_path)

# Inisialisasi koneksi Redis
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# Cache untuk menyimpan nama worker berdasarkan PID agar konsisten
_worker_name_cache = {}
_worker_lock = threading.Lock()

def get_worker_name() -> str:
    """Menghasilkan nama worker unik berdasarkan PID, disimpan di cache lokal."""
    pid = multiprocessing.current_process().pid
    with _worker_lock:
        if pid not in _worker_name_cache:
            index = len(_worker_name_cache) + 1
            _worker_name_cache[pid] = f"WorkerProcess-{index}"
        return _worker_name_cache[pid]

def get_cache_key(input_text: str) -> str:
    """Menghasilkan kunci cache unik menggunakan hash SHA-256 dari input."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def flatten_dict(d, parent_key='', sep='||'):
    """Mengubah dictionary bersarang menjadi datar dengan pemisah khusus."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            # Rekursif jika nilai adalah dictionary
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def make_prediction(method: str, url: str, body, client_ip: str = "Tidak Diketahui", status_code: int = None) -> dict:
    """Fungsi untuk melakukan prediksi berdasarkan input yang diberikan."""
    try:
        now = datetime.datetime.now()
        process_name = get_worker_name()

        # Validasi input
        if method.upper() == "GET":
            input_text = url.strip()
        elif method.upper() == "POST":
            if isinstance(body, dict):
                flat_body = flatten_dict(body)
                body_string = " ".join(f"{k}={v}" for k, v in flat_body.items())
            elif isinstance(body, str):
                body_string = body.strip()
            else:
                body_string = ""
            input_text = f"{url.strip()} {body_string}".strip()
        else:
            input_text = f"{method.strip()} {url.strip()}".strip()

        # Pastikan input tidak kosong
        if not input_text:
            return {"error": "Payload diperlukan"}

        # Buat kunci cache berdasarkan input
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)

        # Buat log umum untuk semua prediksi
        log_common = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "level": "INFO",
            "worker": process_name,
            "ip": client_ip,
            "payload": input_text,
        }
        if status_code is not None:
            log_common["status_code"] = status_code

        # Cek cache Redis untuk hasil prediksi
        if hasil_cache:
            log_common.update({
                "prediction": hasil_cache,
                "cache_hit": True
            })
            current_app.logger.info(json.dumps(log_common))
            return {"prediction": hasil_cache}

        # Jika tidak ada di cache, lakukan prediksi
        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]
        label = {0: "Normal", 1: "SQL Injection", 2: "XSS"}.get(pred, "Tidak Diketahui")

        # Simpan hasil prediksi ke cache Redis dengan waktu kedaluwarsa 60 detik
        redis_client.setex(cache_key, 60, label)

        # Log hasil prediksi
        log_common.update({
            "prediction": label,
            "cache_hit": False
        })
        current_app.logger.info(json.dumps(log_common))
        return {"prediction": label}

    # Tangani kesalahan yang mungkin terjadi
    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "ERROR",
            "worker": get_worker_name(),
            "ip": client_ip,
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}