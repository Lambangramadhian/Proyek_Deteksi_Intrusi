import os
import json
import redis
import joblib
import hashlib
import datetime
from flask import current_app

# Load model dan vectorizer dari folder model/
MODEL_PATH = os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl")
VECTORIZER_PATH = os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl")

# Load model dan vectorizer
model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECTORIZER_PATH)

# Redis host konfigurasi fleksibel
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=0, decode_responses=True)

def get_cache_key(input_text):
    """Menghasilkan kunci cache berdasarkan input text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(input_text, client_ip="Tidak Diketahui", user_agent="Tidak Diketahui"):
    """Fungsi untuk memproses prediksi dan menyimpan hasil ke Redis."""
    try:
        timestamp = datetime.datetime.now().isoformat()

        if not input_text:
            return {"error": "Payload diperlukan"}

        # Log input
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "ip": client_ip,
            "user_agent": user_agent,
            "input": input_text
        }))

        # Cek cache Redis
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(json.dumps({
                "timestamp": timestamp,
                "cache": "hit",
                "prediction": hasil_cache
            }))
            return {"prediction": hasil_cache}

        # Proses prediksi
        input_vectorized = vectorizer.transform([input_text])
        prediction = model.predict(input_vectorized)[0]

        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        prediction_label = label_map.get(prediction, "Tidak Diketahui")

        redis_client.setex(cache_key, 60, prediction_label)

        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "prediction": prediction_label
        }))

        return {"prediction": prediction_label}

    # Handle error dan log
    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}