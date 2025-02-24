from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from logging_config import setup_logging
from auth import token_required, generate_jwt_token
from predict import make_prediction
import joblib
import os
import redis

# Initialize Flask app
app = Flask(__name__)

# Load model & vectorizer
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Get script directory
model_path = os.path.join(BASE_DIR, "svm_intrusion_detection.pkl")
vectorizer_path = os.path.join(BASE_DIR, "tfidf_vectorizer.pkl")

model = joblib.load(model_path)
vectorizer = joblib.load(vectorizer_path)

# Label mapping
label_mapping = {0: "Normal", 1: "XSS", 2: "SQL Injection"}

# Config Secret Key from environment variable
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your_default_secret_key")

# Redis connection setup
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Rate limiter (5 requests per minute per IP using Redis)
limiter = Limiter(get_remote_address, app=app, storage_uri="redis://localhost:6379", default_limits=["5 per minute"])

# Setup logging
setup_logging(app)

# ===================== Routes ===================== #
@app.route("/generate-token", methods=["POST"])
def generate_token():
    return generate_jwt_token(request)

@app.route("/predict", methods=["POST"])
@token_required
@limiter.limit("5 per minute")
def predict():
    return make_prediction(request, model, vectorizer, label_mapping, redis_client)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Intrusion Detection API is running!"}), 200

@app.route("/favicon.ico")
def favicon():
    return "", 204  # No Content

# ===================== Main ===================== #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)