import re
from flask import jsonify, current_app
import hashlib

def make_prediction(request, model, vectorizer, label_mapping, redis_client):
    try:
        data = request.get_json()
        input_text = data.get("text", "")

        # Input validation to prevent SQL Injection/XSS
        if not re.match(r"^[a-zA-Z0-9\s<>()\[\]{}'\";:/+=!@#%^&*-]*$", input_text):
            current_app.logger.warning(f"Blocked Input: {repr(input_text)} from {request.remote_addr}")
            return jsonify({"error": "Invalid input format!", "blocked_input": input_text}), 400


        if not input_text:
            return jsonify({"error": "Input text is required"}), 400

        # Generate a cache key based on input text (using hash for uniqueness)
        cache_key = f"prediction:{hashlib.sha256(input_text.encode()).hexdigest()}"

        # Check if the result is cached in Redis
        cached_result = redis_client.get(cache_key)
        if cached_result:
            current_app.logger.info(f"Cache hit for {request.remote_addr} - Input: {input_text}")
            return jsonify({"prediction": cached_result})

        # Vectorize input text and make a prediction
        text_vectorized = vectorizer.transform([input_text])
        prediction = model.predict(text_vectorized)[0]
        prediction_text = label_mapping[prediction]

        # Cache the prediction result for future requests (TTL: 60 seconds)
        redis_client.setex(cache_key, 60, prediction_text)

        # Log prediction request
        current_app.logger.info(f"Prediction request from {request.remote_addr} - Input: {input_text} - Result: {prediction_text}")

        return jsonify({"prediction": prediction_text})
    except Exception as e:
        current_app.logger.error(f"Server Error: {str(e)}")
        return jsonify({"error": str(e)}), 500