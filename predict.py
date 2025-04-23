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
    """Fungsi untuk memproses prediksi berdasarkan input yang diterima."""
    try:
        timestamp = datetime.datetime.now().isoformat()
        
        # Bangun input_text
        if isinstance(body, dict):
            body_str = json.dumps(body, ensure_ascii=False)
        else:
            body_str = str(body).strip()

        # Format body untuk menghindari karakter khusus
        input_text = f"{method.strip()} {url.strip()} {body_str}".strip()

        # Format payload log JSON (indented)
        structured_payload = {
            "method": method,
            "url": url,
            "body": body
        }

        # Log gaya manusia
        readable_json = json.dumps(structured_payload, indent=4, ensure_ascii=False)
        current_app.logger.info(f"[{timestamp}] IP: {client_ip} | User-Agent: Tidak Diketahui | Input: {readable_json}")

        # Cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Prediksi: {hasil_cache}")
            current_app.logger.info(f"Hasil prediksi: {{'prediction': '{hasil_cache}'}}")
            return {"prediction": hasil_cache}

        # Model
        vectorized = vectorizer.transform([input_text])
        prediction = model.predict(vectorized)[0]
        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label = label_map.get(prediction, "Tidak Diketahui")

        # Cache hasil prediksi
        redis_client.setex(cache_key, 60, label)

        # Log hasil prediksi
        current_app.logger.info(f"[{timestamp}] Prediksi: {label}")
        current_app.logger.info(f"Hasil prediksi: {{'prediction': '{label}'}}")
        return {"prediction": label}
    
    # Menangani kesalahan koneksi Redis
    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}