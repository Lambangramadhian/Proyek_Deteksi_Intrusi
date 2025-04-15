import hashlib
import redis
import datetime
import joblib
import os
import csv
from flask import current_app

model = joblib.load('model/svm_intrusion_detection.pkl')
vectorizer = joblib.load('model/tfidf_vectorizer.pkl')

def get_cache_key(input_text):
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def append_to_csv(timestamp, ip, user_agent, input_text, prediction):
    file_path = 'prediction_log.csv'
    file_exists = os.path.isfile(file_path)

    with open(file_path, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["timestamp", "ip", "user_agent", "input_text", "prediction"])
        writer.writerow([timestamp, ip, user_agent, input_text, prediction])

def make_prediction(input_text, client_ip="Tidak Diketahui", user_agent="Tidak Diketahui"):
    try:
        timestamp = datetime.datetime.now().isoformat()
        current_app.logger.info(f"[{timestamp}] IP: {client_ip} | User-Agent: {user_agent} | Input: {input_text}")

        if not input_text:
            return {"error": "Payload diperlukan"}

        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)

        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Cache hit: {hasil_cache}")
            append_to_csv(timestamp, client_ip, user_agent, input_text, hasil_cache)
            return {"prediction": hasil_cache}

        input_tervektorisasi = vectorizer.transform([input_text])
        prediksi = model.predict(input_tervektorisasi)[0]
        pemetaan_label = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label_prediksi = pemetaan_label.get(prediksi, "Tidak Diketahui")

        redis_client.setex(cache_key, 60, label_prediksi)
        current_app.logger.info(f"[{timestamp}] Prediksi: {label_prediksi}")
        append_to_csv(timestamp, client_ip, user_agent, input_text, label_prediksi)

        return {"prediction": label_prediksi}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Kesalahan Server: {str(e)}")
        return {"error": "Kesalahan server internal"}