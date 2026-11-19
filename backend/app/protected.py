# backend/app/protected.py
"""Protected test blueprint demonstrating JWT verification.
Provides a simple endpoint that returns a greeting using the decoded
JWT payload attached by the @jwt_required decorator.
"""

from flask import Blueprint, jsonify, request
from .decorators import jwt_required

protected_bp = Blueprint("protected", __name__, url_prefix="/protected")

@protected_bp.route("/hello", methods=["GET"])
@jwt_required
def hello():
    user = request.user  # payload injected by the decorator
    return jsonify({
        "message": f"Hello, {user.get('email', 'unknown')}! You are a {user.get('role', 'guest')}."
    })
