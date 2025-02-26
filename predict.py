import re
import hashlib
import redis
import datetime
from flask import current_app

def validate_input(input_text):
    """Detect if the input is a potential SQL Injection or XSS attack."""
    sql_patterns = r"(?i)(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\b--|\b#|/\*|\*/)"
    xss_patterns = r"(?i)(<script|javascript:|onerror=|onload=|alert\()"

    if re.search(sql_patterns, input_text):
        return "SQL Injection"
    elif re.search(xss_patterns, input_text):
        return "XSS"
    return "Normal"

def get_cache_key(input_text):
    """Generate a cache key based on the hashed input text."""
    return f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

def make_prediction(input_text, client_ip="Unknown", user_agent="Unknown"):
    try:
        # Get the current timestamp
        timestamp = datetime.datetime.now().isoformat()

        # Log the input details with IP address and User-Agent
        log_message = f"[{timestamp}] IP: {client_ip} | User-Agent: {user_agent} | Input: {input_text}"
        current_app.logger.info(log_message)

        if not input_text:
            return {"error": "Payload is required"}

        # Create Redis client inside the function
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

        # Check Redis cache first
        cache_key = get_cache_key(input_text)
        cached_result = redis_client.get(cache_key)
        if cached_result:
            current_app.logger.info(f"[{timestamp}] Cache hit: {cached_result}")
            return {"prediction": cached_result}

        # Predict category (Normal, SQL Injection, or XSS)
        prediction_text = validate_input(input_text)

        # Cache the prediction result for 60 seconds
        redis_client.setex(cache_key, 60, prediction_text)

        # Log prediction result
        current_app.logger.info(f"[{timestamp}] Prediction: {prediction_text}")

        return {"prediction": prediction_text}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Server Error: {str(e)}")
        return {"error": "Internal server error"}