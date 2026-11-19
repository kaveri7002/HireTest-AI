# backend/app/decorators.py
"""Utility decorators for authentication.
Provides a simple @jwt_required decorator that validates the JWT
sent in the `Authorization: Bearer <token>` header and injects the
decoded payload into `request.user`.
"""

import functools
from flask import request, jsonify, current_app
import jwt


def jwt_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Missing or malformed Authorization header"}), 401
        token = parts[1]
        try:
            payload = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        # Attach payload to request for downstream use
        request.user = payload
        return fn(*args, **kwargs)
    return wrapper
