import re
import hashlib
import redis
import datetime
from flask import current_app

def validate_input(input_text):
    """Deteksi apakah input berpotensi serangan SQL Injection atau XSS."""
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
        # Dapatkan timestamp saat ini
        timestamp = datetime.datetime.now().isoformat()

        # Catat detail input dengan alamat IP dan User-Agent
        pesan_log = f"[{timestamp}] IP: {client_ip} | User-Agent: {user_agent} | Input: {input_text}"
        current_app.logger.info(pesan_log)

        if not input_text:
            return {"error": "Payload diperlukan"}

        # Buat client Redis di dalam fungsi
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

        # Periksa cache Redis terlebih dahulu
        cache_key = get_cache_key(input_text)
        hasil_cache = redis_client.get(cache_key)
        if hasil_cache:
            current_app.logger.info(f"[{timestamp}] Cache hit: {hasil_cache}")
            return {"prediction": hasil_cache}

        # Prediksi kategori (Normal, SQL Injection, atau XSS)
        teks_prediksi = validate_input(input_text)

        # Cache hasil prediksi selama 60 detik
        redis_client.setex(cache_key, 60, teks_prediksi)

        # Catat hasil prediksi
        current_app.logger.info(f"[{timestamp}] Prediksi: {teks_prediksi}")

        return {"prediction": teks_prediksi}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Kesalahan Server: {str(e)}")
        return {"error": "Kesalahan server internal"}