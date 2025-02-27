import re
import hashlib
import redis
import datetime
import joblib
from flask import current_app

# Load the model and vectorizer
model = joblib.load('svm_intrusion_detection.pkl')
vectorizer = joblib.load('tfidf_vectorizer.pkl')

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

        # Optional pre-validation using basic rules (fail-safe)
        pre_validation_result = validate_input(input_text)
        if pre_validation_result != "Normal":
            current_app.logger.info(f"[{timestamp}] Pre-validation detected: {pre_validation_result}")
            return {"prediction": pre_validation_result}  # Early return for obvious attacks

        # Create Redis client inside the function
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

        # Check Redis cache first
        cache_key = get_cache_key(input_text)
        cached_result = redis_client.get(cache_key)
        if cached_result:
            current_app.logger.info(f"[{timestamp}] Cache hit: {cached_result}")
            return {"prediction": cached_result}

        # Preprocess the input using the vectorizer (transform the input text into numerical features)
        input_vectorized = vectorizer.transform([input_text])

        # Use the model to make a prediction
        prediction = model.predict(input_vectorized)[0]

        # Map the prediction to a human-readable label
        label_mapping = {0: "Normal", 1: "XSS", 2: "SQL Injection"}
        prediction_label = label_mapping.get(prediction, "Unknown")

        # Cache the prediction result for 60 seconds
        redis_client.setex(cache_key, 60, prediction_label)

        # Log the prediction result
        current_app.logger.info(f"[{timestamp}] Prediction: {prediction_label}")

        return {"prediction": prediction_label}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Server Error: {str(e)}")
        return {"error": "Internal server error"}