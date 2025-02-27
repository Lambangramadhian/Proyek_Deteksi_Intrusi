import re
import hashlib
import redis
import datetime
import joblib  # Import joblib to load the model and vectorizer
from flask import current_app

# Load the model and vectorizer
model = joblib.load('svm_intrusion_detection.pkl')  # Load the pre-trained SVM model
vectorizer = joblib.load('tfidf_vectorizer.pkl')  # Load the pre-trained TF-IDF vectorizer

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

        # Preprocess the input using the vectorizer (transform the input text into numerical features)
        input_vectorized = vectorizer.transform([input_text])

        # Use the model to make a prediction
        prediction = model.predict(input_vectorized)[0]

        # Map the prediction to a human-readable label
        label_mapping = {0: "Normal", 1: "SQL Injection", 2: "XSS"}  # Adjust the mapping based on your model's output
        prediction_label = label_mapping.get(prediction, "Unknown")

        # Cache the prediction result for 60 seconds
        redis_client.setex(cache_key, 60, prediction_label)

        # Log the prediction result
        current_app.logger.info(f"[{timestamp}] Prediction: {prediction_label}")

        return {"prediction": prediction_label}

    except Exception as e:
        current_app.logger.error(f"[{timestamp}] Server Error: {str(e)}")
        return {"error": "Internal server error"}   