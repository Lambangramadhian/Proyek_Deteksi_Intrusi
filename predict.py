# Import pustaka yang dibutuhkan
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

def make_prediction(method: str, url: str, body, client_ip: str = "Tidak Diketahui", user_id: str = "Tidak Diketahui") -> dict:
    """Melakukan prediksi berdasarkan metode, URL, dan body payload, lalu log hasilnya."""
    try:
        now = datetime.datetime.now()
        process_name = get_worker_name()

        # Persiapkan body menjadi string
        if isinstance(body, dict):
            flat_body = flatten_dict(body)
            body_string = " ".join(f"{k}={v}" for k, v in flat_body.items())
        elif isinstance(body, str):
            body_string = body.strip()
        else:
            body_string = ""

        # Gabungkan method, URL, dan body untuk dijadikan input ke model
        input_text = f"{method.strip()} {url.strip()} {body_string}".strip()
        if not input_text:
            return {"error": "Payload diperlukan"}

        # Gunakan cache Redis jika prediksi sebelumnya sudah tersedia
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)

        if hasil_cache:
            # Log jika prediksi diambil dari cache
            log_payload = {
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "level": "INFO",
                "worker": process_name,
                "ip": client_ip,
                "user_id": user_id,
                "payload": input_text,
                "prediction": hasil_cache,
                "cache_hit": True
            }
            current_app.logger.info(json.dumps(log_payload))
            return {"prediction": hasil_cache}

        # Transform input ke dalam bentuk vektor dan prediksi dengan model
        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]

        # Peta label hasil prediksi
        label_map = {0: "Normal", 1: "SQL Injection", 2: "XSS"}
        label = label_map.get(pred, "Tidak Diketahui")

        # Simpan hasil ke Redis untuk cache di masa depan (60 detik)
        redis_client.setex(cache_key, 60, label)

        # Log hasil prediksi baru
        log_payload = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "level": "INFO",
            "worker": process_name,
            "ip": client_ip,
            "user_id": user_id,
            "payload": input_text,
            "prediction": label,
            "cache_hit": False
        }
        current_app.logger.info(json.dumps(log_payload))
        return {"prediction": label}

    except Exception as e:
        # Tangani error dan log dalam format terstruktur
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "ERROR",
            "worker": get_worker_name(),
            "ip": client_ip,
            "user_id": user_id,
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}