import jwt
import datetime
from functools import wraps
from flask import request, jsonify, current_app

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("x-access-token")
        if not token:
            current_app.logger.warning(f"Unauthorized Access Attempt from {request.remote_addr}")
            return jsonify({"error": "Token is missing!"}), 401
        try:
            data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            current_app.logger.warning(f"Expired Token Used from {request.remote_addr}")
            return jsonify({"error": "Token expired!"}), 401
        except jwt.InvalidTokenError:
            current_app.logger.warning(f"Invalid Token Attempt from {request.remote_addr}")
            return jsonify({"error": "Invalid token!"}), 401
        return f(*args, **kwargs)
    return decorated

def generate_jwt_token(request):
    auth = request.json
    if auth and auth.get("username") == "admin" and auth.get("password") == "password":
        token = jwt.encode(
            {"user": auth["username"], "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)},
            current_app.config["SECRET_KEY"],
            algorithm="HS256"
        )
        current_app.logger.info(f"Token generated for {auth['username']} from {request.remote_addr}")
        return jsonify({"token": token})
    current_app.logger.warning(f"Failed login attempt from {request.remote_addr}")
    return jsonify({"error": "Invalid credentials!"}), 401