import os
import json
import redis
import joblib
import hashlib
import datetime
import re
from flask import current_app

# Load model and vectorizer from environment variables or default paths
model = joblib.load(os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl"))
vectorizer = joblib.load(os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl"))

# Inisialisasi Redis client
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

def get_cache_key(input_text):
    """Generate a unique cache key based on the input text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(method, url, body, client_ip="Tidak Diketahui"):
    """Fungsi untuk memproses prediksi berdasarkan method, url, dan body."""
    try:
        timestamp = datetime.datetime.now().isoformat()

        # Gabungkan menjadi satu string sesuai format
        parts = [method.strip(), url.strip()]
        if isinstance(body, dict):
            parts.append(json.dumps(body, ensure_ascii=False))
        elif isinstance(body, str):
            parts.append(body.strip())

        # Jika body tidak ada, gunakan string kosong
        input_text = " ".join(parts).strip()

        # Debug langsung ke konsol
        print("[DEBUG] Final input_text:", input_text)

        # Logging input
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "ip": client_ip,
            "input": input_text
        }))

        # Validasi input
        if not input_text:
            return {"error": "Payload diperlukan"}

        # Redis: check cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(json.dumps({
                "timestamp": timestamp,
                "cache": "hit",
                "prediction": hasil_cache
            }))
            return {"prediction": hasil_cache}

        # Vectorize + Predict
        input_vec = vectorizer.transform([input_text])
        pred = model.predict(input_vec)[0]

        # Map label ke nama
        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label = label_map.get(pred, "Tidak Diketahui")

        # Simpan hasil prediksi ke Redis dengan waktu kedaluwarsa 60 detik
        redis_client.setex(cache_key, 60, label)

        # Logging hasil prediksi
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "prediction": label
        }))
        return {"prediction": label}

    # Menangani kesalahan koneksi Redis
    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}