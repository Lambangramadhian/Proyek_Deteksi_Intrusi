import os
import json
import redis
import joblib
import hashlib
import datetime
from flask import current_app

# Load model dan vectorizer dari env atau default
model = joblib.load(os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl"))
vectorizer = joblib.load(os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl"))

# Redis global instance
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

def get_cache_key(input_text):
    """Menghasilkan kunci cache berdasarkan input_text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(input_text, client_ip="Tidak Diketahui"):
    """Fungsi untuk memproses prediksi dengan model dan menyimpan hasil ke Redis."""
    try:
        timestamp = datetime.datetime.now().isoformat()

        # Mendapatkan informasi IP dan User-Agent dari header permintaan
        if not input_text:
            return {"error": "Payload diperlukan"}

        # Log input
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "ip": client_ip,
            "input": input_text
        }))

        # Redis cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(json.dumps({
                "timestamp": timestamp,
                "cache": "hit",
                "prediction": hasil_cache
            }))
            return {"prediction": hasil_cache}

        # Vektorisasi dan prediksi
        vectorized_input = vectorizer.transform([input_text])
        prediction = model.predict(vectorized_input)[0]

        # Map label ke string
        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label = label_map.get(prediction, "Tidak Diketahui")

        # Simpan hasil prediksi ke Redis dengan waktu kedaluwarsa 60 detik
        redis_client.setex(cache_key, 60, label)

        # Log hasil prediksi
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "prediction": label
        }))
        return {"prediction": label}

    # Handle exception and log error
    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}