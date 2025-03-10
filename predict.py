import re
import hashlib
import redis
import datetime
import joblib
from flask import current_app

# Muat model dan vectorizer
model = joblib.load('svm_intrusion_detection.pkl')
vectorizer = joblib.load('tfidf_vectorizer.pkl')

def validate_input(input_text):
    """Deteksi serangan SQL Injection atau XSS menggunakan pola dasar."""
    pola_sql = r"(?i)(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\b--|\b#|/\*|\*/)"
    pola_xss = r"(?i)(<script|javascript:|onerror=|onload=|alert\()"

    if re.search(pola_sql, input_text):
        return "SQL Injection"
    elif re.search(pola_xss, input_text):
        return "XSS"
    return "Normal"

def get_cache_key(input_text):
    """Hasilkan cache key berdasarkan teks input yang di-hash."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(input_text, client_ip="Tidak Diketahui", user_agent="Tidak Diketahui"):
    try:
        timestamp = datetime.datetime.now().isoformat()

        # Catat input sekali dengan IP dan User-Agent
        pesan_log = f"[{timestamp}] IP: {client_ip} | User-Agent: {user_agent} | Input: {input_text}"
        current_app.logger.info(pesan_log)

        if not input_text:
            return {"error": "Payload diperlukan"}

        # Validasi awal menggunakan aturan dasar
        validasi_awal = validate_input(input_text)
        if validasi_awal != "Normal":
            current_app.logger.info(f"[{timestamp}] Validasi awal mendeteksi: {validasi_awal}")
            return {"prediction": validasi_awal}

        # Inisialisasi klien Redis
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

        # Periksa cache Redis terlebih dahulu
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Cache hit: {hasil_cache}")
            return {"prediction": hasil_cache}

        # Vektorkan teks input
        input_tervektorisasi = vectorizer.transform([input_text])

        # Prediksi menggunakan model
        prediksi = model.predict(input_tervektorisasi)[0]

        # Peta prediksi ke label yang mudah dibaca manusia
        pemetaan_label = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        label_prediksi = pemetaan_label.get(prediksi, "Tidak Diketahui")

        # Cache hasil prediksi selama 60 detik
        redis_client.setex(cache_key, 60, label_prediksi)

        # Catat dan kembalikan hasil prediksi
        current_app.logger.info(f"[{timestamp}] Prediksi: {label_prediksi}")
        return {"prediction": label_prediksi}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Kesalahan Server: {str(e)}")
        return {"error": "Kesalahan server internal"}