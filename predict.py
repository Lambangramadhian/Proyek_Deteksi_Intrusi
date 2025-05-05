import os
import json
import redis
import joblib
import hashlib
import datetime
from flask import current_app

model = joblib.load(os.getenv("MODEL_PATH", "model/random_forest_web_ids.pkl"))
vectorizer = joblib.load(os.getenv("VECTORIZER_PATH", "model/tfidf_vectorizer.pkl"))

redis_client = redis.StrictRedis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)


def get_cache_key(input_text: str) -> str:
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"


def make_prediction(method: str, url: str, body, client_ip: str = "Tidak Diketahui", user_id: str = "Tidak Diketahui") -> dict:
    try:
        now = datetime.datetime.now()
        timestamp_str = now.strftime("[%d/%m/%Y %H:%M:%S]")

        if isinstance(body, dict):
            body_string = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        elif isinstance(body, str):
            body_string = body.strip()
        else:
            body_string = ""

        input_text = f"{method.strip()} {url.strip()} {body_string}".strip()

        if not input_text:
            return {"error": "Payload diperlukan"}

        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            _log_prediction(timestamp_str, client_ip, user_id, method, url, body, hasil_cache)
            return {"prediction": hasil_cache}

        input_vector = vectorizer.transform([input_text])
        pred = model.predict(input_vector)[0]

        label_map = {0: "Normal", 1: "SQL Injection", 2: "XSS"}
        label = label_map.get(pred, "Tidak Diketahui")

        redis_client.setex(cache_key, 60, label)
        _log_prediction(timestamp_str, client_ip, user_id, method, url, body, label)

        return {"prediction": label}

    except Exception as e:
        error_ts = datetime.datetime.now().strftime("[%d/%m/%Y %H:%M:%S]")
        current_app.logger.error(json.dumps({
            "timestamp": error_ts,
            "error": str(e)
        }))
        return {"error": "Kesalahan server internal"}


def _log_prediction(timestamp_str, ip, user_id, method, url, body, label):
    formatted_input = json.dumps({
        "method": method,
        "url": url,
        "body": body
    }, indent=4, ensure_ascii=False)

    current_app.logger.info(f"{timestamp_str} IP: {ip} | User-ID: {user_id} | Input: {formatted_input}")
    current_app.logger.info(f"{timestamp_str} Prediksi: {label}")
    current_app.logger.info(f"{timestamp_str} Hasil prediksi: {{'prediction': '{label}'}}")