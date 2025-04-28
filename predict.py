import os
import json
import redis
import joblib
import hashlib
import datetime
from flask import current_app

# Load model dan vectorizer dari environment atau default
model = joblib.load(os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl"))
vectorizer = joblib.load(os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl"))

# Koneksi Redis
redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

def get_cache_key(input_text):
    """Generate a unique cache key based on the input text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(method, url, body, client_ip="Tidak Diketahui", user_id="Tidak Diketahui"):
    """Memproses prediksi dan mencatat hasilnya dengan format log terstruktur."""
    try:
        timestamp = datetime.datetime.now().isoformat()

        if isinstance(body, dict):
            body_str = json.dumps(body, ensure_ascii=False)
        else:
            body_str = str(body).strip()

        input_text = f"{method.strip()} {url.strip()} {body_str}".strip()

        # Format JSON untuk log
        structured_payload = {
            "method": method,
            "url": url,
            "body": body
        }

        readable_json = json.dumps(structured_payload, indent=4, ensure_ascii=False)

        # LOG: Input diterima
        current_app.logger.info(
            f"[{timestamp}] IP: {client_ip} | User-ID: {user_id} | Input: {readable_json}"
        )

        if not input_text:
            return {"error": "Payload diperlukan"}

        # Cek di Redis Cache
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Prediksi: {hasil_cache}")
            current_app.logger.info(f"Hasil prediksi: {{'prediction': '{hasil_cache}'}}")
            return {"prediction": hasil_cache}

        # Vektorisasi & Prediksi
        input_vectorized = vectorizer.transform([input_text])
        prediction = model.predict(input_vectorized)[0]

        label_map = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label = label_map.get(prediction, "Tidak Diketahui")

        # Simpan hasil prediksi ke Redis
        redis_client.setex(cache_key, 60, label)

        # LOG: Hasil prediksi
        current_app.logger.info(f"[{timestamp}] Prediksi: {label}")
        current_app.logger.info(f"Hasil prediksi: {{'prediction': '{label}'}}")

        return {"prediction": label}

    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}