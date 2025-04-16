import hashlib
import redis
import datetime
import joblib
import json
from flask import current_app

# Load model and vectorizer
model = joblib.load('model/svm_intrusion_detection.pkl')
vectorizer = joblib.load('model/tfidf_vectorizer.pkl')

def get_cache_key(input_text):
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(input_text, client_ip="Tidak Diketahui", user_agent="Tidak Diketahui"):
    try:
        timestamp = datetime.datetime.now().isoformat()

        # Log input in structured JSON format
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "ip": client_ip,
            "user_agent": user_agent,
            "input": input_text
        }))

        if not input_text:
            return {"error": "Payload diperlukan"}

        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Cache hit: {hasil_cache}")
            return {"prediction": hasil_cache}

        # Vectorize input and predict
        input_tervektorisasi = vectorizer.transform([input_text])
        prediksi = model.predict(input_tervektorisasi)[0]

        # Map prediction to label
        pemetaan_label = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label_prediksi = pemetaan_label.get(prediksi, "Tidak Diketahui")

        # Cache prediction
        redis_client.setex(cache_key, 60, label_prediksi)

        # Log result
        current_app.logger.info(json.dumps({
            "timestamp": timestamp,
            "prediction": label_prediksi
        }))

        return {"prediction": label_prediksi}

    except Exception as e:
        current_app.logger.error(json.dumps({
            "timestamp": datetime.datetime.now().isoformat(),
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}