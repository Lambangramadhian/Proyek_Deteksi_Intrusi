import os
import json
import redis
import joblib
import hashlib
import datetime
from flask import current_app

# Load model dan vectorizer dari environment variables atau default
model = joblib.load(os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl"))
vectorizer = joblib.load(os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl"))

# Redis Client
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

def get_cache_key(input_text: str) -> str:
    """Buat cache key dari input_text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(method: str, url: str, body, client_ip: str = "Tidak Diketahui") -> dict:
    """Prediksi payload berdasarkan method + url + body."""
    try:
        timestamp = datetime.datetime.now().isoformat()

        # Gabungkan method + url + body ke format training yang konsisten
        parts = [method.strip(), url.strip()]
        if isinstance(body, dict):
            parts.append(json.dumps(body, separators=(',', ':'), ensure_ascii=False))  # Tanpa spasi berlebih
        elif isinstance(body, str):
            parts.append(body.strip())

        input_text = " ".join(parts).strip()

        # Log input structured readable
        structured_log = {
            "method": method,
            "url": url,
            "body": body
        }
        formatted_input = json.dumps(structured_log, indent=4, ensure_ascii=False)
        current_app.logger.info(f"[{timestamp}] IP: {client_ip} | Input: {formatted_input}")

        if not input_text:
            return {"error": "Payload diperlukan"}

        # Check Cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Prediksi: {hasil_cache}")
            current_app.logger.info(f"Hasil prediksi: {{'prediction': '{hasil_cache}'}}")
            return {"prediction": hasil_cache}

        # Predict from model
        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]

        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label = label_map.get(pred, "Tidak Diketahui")

        # Simpan ke Cache Redis
        redis_client.setex(cache_key, 60, label)

        # Log hasil prediksi
        current_app.logger.info(f"[{timestamp}] Prediksi: {label}")
        current_app.logger.info(f"Hasil prediksi: {{'prediction': '{label}'}}")

        return {"prediction": label}

    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}