# =====================
# Library Standar Python (Standard Library)
# =====================
import os                                # Operasi sistem file & environment variable
import json                              # Serialisasi dan deserialisasi objek JSON
import hashlib                           # Membuat hash data (misalnya untuk verifikasi atau identifikasi)
import datetime                          # Operasi tanggal dan waktu
import multiprocessing                   # Menjalankan proses paralel (multi-core)
import threading                         # Menjalankan thread paralel (lebih ringan dari proses)
import urllib.parse                      # Parsing dan manipulasi komponen URL

# =====================
# Library Pihak Ketiga (Third-party Libraries)
# =====================
import redis                             # Redis client – koneksi ke Redis server
import joblib                            # Untuk menyimpan dan memuat model Machine Learning (seperti dengan pickle)
from flask import current_app            # Flask – mengakses konteks aplikasi aktif

# =====================
# Modul Internal Proyek (Local Project Modules)
# =====================
from utils import (
    flatten_dict,                        # Mengubah nested dictionary menjadi flat dictionary
    parse_payload                        # Parsing dan validasi payload dari request
)

# Inisialisasi direktori model dan memuat model serta vectorizer
model_dir = 'model'
os.makedirs(model_dir, exist_ok=True)
model_path = os.getenv("MODEL_PATH", os.path.join(model_dir, "random_forest_web_ids.pkl"))
vectorizer_path = os.getenv("VECTORIZER_PATH", os.path.join(model_dir, "tfidf_vectorizer.pkl"))

# Memastikan model dan vectorizer ada
try:
    model = joblib.load(model_path)
    vectorizer = joblib.load(vectorizer_path)
except Exception as e:
    raise RuntimeError(f"Gagal memuat model/vectorizer: {e}")

# Inisialisasi koneksi Redis
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# Validasi koneksi Redis
_worker_name_cache = {}
_worker_lock = threading.Lock()

def get_worker_name() -> str:
    """Mengembalikan nama unik untuk proses worker saat ini."""
    pid = multiprocessing.current_process().pid
    with _worker_lock:
        if pid not in _worker_name_cache:
            _worker_name_cache[pid] = f"WorkerProcess-{len(_worker_name_cache) + 1}"
        return _worker_name_cache[pid]

def parse_body_to_input_text(method, url, body) -> str:
    """ Mengonversi body permintaan HTTP menjadi string input untuk model."""
    method = method.upper() if method else ""
    url = url.strip() if url else ""

    # Decode jika body dikirim sebagai string URL-encoded
    if isinstance(body, str):
        try:
            decoded = urllib.parse.unquote_plus(body)
            body = dict(urllib.parse.parse_qsl(decoded))
        except Exception:
            body = {"raw": body}

    # Jika ada field "raw" di dalam dict, coba parse kembali
    if isinstance(body, dict) and "raw" in body:
        try:
            decoded = urllib.parse.unquote_plus(body["raw"])
            parsed = dict(urllib.parse.parse_qsl(decoded))
            body.update(parsed)
            body.pop("raw", None)
        except Exception:
            pass

    # Jika body masih berupa string, simpan sebagai "raw"
    flat_body = flatten_dict(body)
    body_string = " ".join(f"{k}={v}" for k, v in flat_body.items())

    # Final input untuk TF-IDF vectorizer: PARAMETER FLATTENED
    return body_string.strip()

# Daftar label untuk prediksi
LABELS = {0: "Normal", 1: "SQL Injection", 2: "XSS"}

def predict_label(input_text: str) -> str:
    """Memprediksi label dari input teks menggunakan model dan vectorizer."""
    input_vector = vectorizer.transform([input_text])
    pred = model.predict(input_vector)[0]
    return LABELS.get(pred, "Tidak Diketahui")

def make_prediction(method, url, body, client_ip):
    """Fungsi utama untuk membuat prediksi berdasarkan input HTTP request."""
    try:
        parsed = parse_payload(body, url=url, ip=client_ip)
        flat = flatten_dict(parsed)
        input_text = " ".join(f"{k}={v}" for k, v in flat.items()).strip()
        cache_key = f"prediction:{method}:{hashlib.sha256(input_text.encode()).hexdigest()}"

        # Cek cache Redis
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            return {"prediction": hasil_cache, "cache_hit": True}

        # Jika tidak ada di cache, lakukan prediksi
        label = predict_label(input_text)
        redis_client.setex(cache_key, 60, label)
        return {"prediction": label, "cache_hit": False}

    # Jika terjadi kesalahan, log error dan kembalikan pesan kesalahan
    except Exception as e:
        log_data = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "ERROR",
            "worker": get_worker_name(),
            "ip": client_ip,
            "error": str(e)
        }
        try:
            current_app.logger.error(json.dumps(log_data))
        except RuntimeError:
            import logging
            logging.basicConfig(level=logging.ERROR)
            logging.error(json.dumps(log_data))
        return {"error": "Kesalahan server internal"}