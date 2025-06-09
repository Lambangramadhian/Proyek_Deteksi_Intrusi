# Import library standar dan eksternal
import os
import json
import redis
import joblib
import hashlib
import datetime
import multiprocessing
import threading
import urllib.parse
from multiprocessing import current_process

# Import dari modul internal
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

def make_prediction(method, url, body, client_ip, status_code=None):
    try:
        # Normalisasi method ke uppercase
        method = method.upper()
        now = datetime.datetime.now()

        # ✅ Handle body string mentah (bukan dict)
        if isinstance(body, str):
            try:
                decoded = urllib.parse.unquote_plus(body)
                parsed = dict(urllib.parse.parse_qsl(decoded))
                body = parsed
            except Exception:
                body = {"raw": body}

        # ✅ Jika dict dan mengandung 'raw', parse lagi
        if isinstance(body, dict) and "raw" in body and isinstance(body["raw"], str):
            try:
                decoded = urllib.parse.unquote_plus(body["raw"])
                parsed = dict(urllib.parse.parse_qsl(decoded))
                body.update(parsed)
                body.pop("raw", None)  # opsional: buang agar log bersih
            except Exception:
                pass

        # 🔁 Flatten dict untuk menyatukan nested body
        def flatten_dict(d, parent_key='', sep='||'):
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        flat_body = flatten_dict(body)
        body_string = " ".join(f"{k}={v}" for k, v in flat_body.items())
        input_text = f"{method} {url.strip()} {body_string}".strip()

        # 🔐 Gunakan hash untuk cache key agar aman & efisien
        hashed_input = hashlib.sha256(input_text.encode()).hexdigest()
        cache_key = f"prediction:{method}:{hashed_input}"

        # 🔍 Cek cache Redis
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            return {
                "prediction": hasil_cache,
                "cache_hit": True
            }

        # 🧠 Prediksi model
        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]
        label = {0: "Normal", 1: "SQL Injection", 2: "XSS"}.get(pred, "Tidak Diketahui")

        # 💾 Simpan hasil ke Redis selama 60 detik
        redis_client.setex(cache_key, 60, label)

        return {
            "prediction": label,
            "cache_hit": False
        }

    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "ERROR",
            "worker": get_worker_name(),
            "ip": client_ip,
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}