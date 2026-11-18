import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

socketio = SocketIO(cors_allowed_origins=[])


class ConfigurationError(RuntimeError):
    pass


def _utc_now():
    return datetime.now(timezone.utc)


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="hiretest-auth-v1")


def _database():
    database = current_app.extensions.get("hiretest_database")
    if database is None:
        raise ConfigurationError("MongoDB is not configured. Set MONGODB_URI in the backend environment.")
    return database


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"error": "Send a valid JSON object."}), 400)
    return body, None


def _user_payload(user):
    return {"id": str(user["_id"]), "name": user["name"], "email": user["email"], "role": user["role"]}


def _authorized_user():
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        user_id = _serializer().loads(token, max_age=current_app.config["TOKEN_MAX_AGE_SECONDS"])
    except (BadSignature, SignatureExpired):
        return None
    try:
        return _database()["users"].find_one({"_id": ObjectId(user_id)})
    except (ValueError, PyMongoError):
        return None


def require_user(*roles):
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            user = _authorized_user()
            if user is None:
                return jsonify({"error": "Sign in to continue."}), 401
            if roles and user.get("role") not in roles:
                return jsonify({"error": "Your account role cannot perform this action."}), 403
            g.user = user
            return handler(*args, **kwargs)

        return wrapped

    return decorator


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_urlsafe(48),
        TOKEN_MAX_AGE_SECONDS=int(os.getenv("TOKEN_MAX_AGE_SECONDS", "86400")),
        MONGODB_URI=os.getenv("MONGODB_URI"),
        MONGODB_DATABASE=os.getenv("MONGODB_DATABASE", "hiretest_ai"),
        FRONTEND_ORIGINS=os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
        FRONTEND_DIST_DIR=str(Path(__file__).resolve().parents[1] / "frontend" / "dist"),
        TESTING=False,
    )
    if test_config:
        app.config.update(test_config)

    mongo_client = app.config.get("MONGO_CLIENT")
    if mongo_client is not None:
        app.extensions["hiretest_mongo_client"] = mongo_client
        app.extensions["hiretest_database"] = mongo_client[app.config["MONGODB_DATABASE"]]
    elif app.config.get("MONGODB_URI"):
        mongo_client = MongoClient(app.config["MONGODB_URI"], serverSelectionTimeoutMS=5000)
        app.extensions["hiretest_mongo_client"] = mongo_client
        app.extensions["hiretest_database"] = mongo_client[app.config["MONGODB_DATABASE"]]
    app.extensions["hiretest_indexes_ready"] = False

    origins = [origin.strip() for origin in app.config["FRONTEND_ORIGINS"].split(",") if origin.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}}, allow_headers=["Content-Type", "Authorization"])
    socketio.init_app(app, cors_allowed_origins=origins)

    @app.before_request
    def ensure_database_indexes():
        database = app.extensions.get("hiretest_database")
        if database is None or app.extensions["hiretest_indexes_ready"]:
            return
        try:
            database["users"].create_index("email", unique=True)
            database["jobs"].create_index([("status", 1), ("created_at", -1)])
            database["applications"].create_index([("student_id", 1), ("job_id", 1)], unique=True)
            database["test_cases"].create_index([("created_by", 1), ("created_at", -1)])
            database["test_executions"].create_index([("created_by", 1), ("created_at", -1)])
            database["test_results"].create_index([("created_by", 1), ("created_at", -1)])
        except PyMongoError:
            current_app.logger.exception("Could not initialize MongoDB indexes.")
            return jsonify({"error": "Database is unavailable. Check the MongoDB connection settings."}), 503
        app.extensions["hiretest_indexes_ready"] = True

    @app.get("/api/health")
    def health():
        if app.extensions.get("hiretest_database") is None:
            return jsonify({"status": "degraded", "database": "not_configured"}), 503
        try:
            _database().command("ping")
        except PyMongoError:
            current_app.logger.exception("MongoDB health check failed.")
            return jsonify({"status": "degraded", "database": "unavailable"}), 503
        return jsonify({"status": "ok", "database": "connected"})

    @app.get("/api/dashboard")
    @require_user()
    def dashboard():
        database = _database()
        try:
            owner = g.user["_id"]
            total = database["test_results"].count_documents({"created_by": owner})
            passed = database["test_results"].count_documents({"created_by": owner, "status": "PASSED"})
            failed = database["test_results"].count_documents({"created_by": owner, "status": "FAILED"})
            blocked = database["test_results"].count_documents({
                "created_by": owner,
                "status": {"$in": ["ERROR", "BLOCKED", "SKIPPED"]},
            })
            executions = list(
                database["test_executions"]
                .find({"created_by": owner}, {"status": 1, "created_at": 1, "duration_ms": 1})
                .sort("created_at", -1)
                .limit(8)
            )
            recent = [
                {
                    "id": str(run["_id"]),
                    "status": run["status"],
                    "createdAt": run["created_at"].isoformat(),
                    "durationMs": run.get("duration_ms"),
                }
                for run in executions
            ]
            return jsonify({
                "total": total,
                "passed": passed,
                "failed": failed,
                "blocked": blocked,
                "recentExecutions": recent,
            })
        except PyMongoError:
            current_app.logger.exception("Could not load testing dashboard from MongoDB.")
            return jsonify({"error": "Testing data is temporarily unavailable."}), 503

    @app.post("/api/auth/register")
    def register():
        body, error = _json_body()
        if error:
            return error
        name = body.get("name", "").strip() if isinstance(body.get("name", ""), str) else ""
        email = body.get("email", "").strip().lower() if isinstance(body.get("email", ""), str) else ""
        password = body.get("password")
        role = body.get("role", "student")
        if not name or len(name) > 80:
            return jsonify({"error": "Name is required and must be 80 characters or fewer."}), 400
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            return jsonify({"error": "Enter a valid email address."}), 400
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            return jsonify({"error": "Password must be between 8 and 128 characters."}), 400
        if not isinstance(role, str) or role not in {"student", "recruiter"}:
            return jsonify({"error": "Choose student or recruiter account type."}), 400
        database = _database()
        user = {
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "created_at": _utc_now(),
        }
        try:
            database["users"].insert_one(user)
        except DuplicateKeyError:
            return jsonify({"error": "An account with that email already exists."}), 409
        token = _serializer().dumps(str(user["_id"]))
        return jsonify({"token": token, "user": _user_payload(user)}), 201

    @app.post("/api/auth/login")
    def login():
        body, error = _json_body()
        if error:
            return error
        email = body.get("email", "").strip().lower() if isinstance(body.get("email", ""), str) else ""
        password = body.get("password")
        user = _database()["users"].find_one({"email": email}) if email else None
        if not user or not isinstance(password, str) or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Email or password is incorrect."}), 401
        token = _serializer().dumps(str(user["_id"]))
        return jsonify({"token": token, "user": _user_payload(user)})

    @app.get("/api/auth/me")
    @require_user()
    def me():
        return jsonify({"user": _user_payload(g.user)})

    @app.get("/api/jobs")
    def list_jobs():
        query = request.args.get("search", "").strip()
        filters = {"status": "published"}
        if query:
            safe_query = re.escape(query[:100])
            filters["$or"] = [
                {"title": {"$regex": safe_query, "$options": "i"}},
                {"company": {"$regex": safe_query, "$options": "i"}},
                {"location": {"$regex": safe_query, "$options": "i"}},
            ]
        jobs = list(_database()["jobs"].find(filters).sort("created_at", -1).limit(100))
        return jsonify({"jobs": [
            {
                "id": str(job["_id"]),
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "type": job.get("type", "Full time"),
                "description": job["description"],
            }
            for job in jobs
        ]})

    @app.post("/api/jobs")
    @require_user("recruiter")
    def create_job():
        body, error = _json_body()
        if error:
            return error
        fields = {}
        for field, limit in (("title", 120), ("company", 120), ("location", 120), ("description", 5000)):
            value = body.get(field)
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                return jsonify({"error": f"{field.title()} is required and must be {limit} characters or fewer."}), 400
            fields[field] = value.strip()
        job = {
            **fields,
            "type": body.get("type", "Full time"),
            "status": "published",
            "recruiter_id": g.user["_id"],
            "created_at": _utc_now(),
        }
        result = _database()["jobs"].insert_one(job)
        return jsonify({"job": {
            "id": str(result.inserted_id),
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "type": job["type"],
            "description": job["description"],
        }}), 201

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id):
        if not ObjectId.is_valid(job_id):
            return jsonify({"error": "Job not found."}), 404
        job = _database()["jobs"].find_one({"_id": ObjectId(job_id), "status": "published"})
        if job is None:
            return jsonify({"error": "Job not found."}), 404
        return jsonify({"job": {
            "id": str(job["_id"]),
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "type": job.get("type", "Full time"),
            "description": job["description"],
        }})

    @app.post("/api/jobs/<job_id>/applications")
    @require_user("student")
    def apply_to_job(job_id):
        if not ObjectId.is_valid(job_id):
            return jsonify({"error": "Job not found."}), 404
        database = _database()
        job = database["jobs"].find_one({"_id": ObjectId(job_id), "status": "published"})
        if job is None:
            return jsonify({"error": "Job not found."}), 404
        application = {
            "job_id": job["_id"],
            "student_id": g.user["_id"],
            "status": "submitted",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        try:
            result = database["applications"].insert_one(application)
        except DuplicateKeyError:
            return jsonify({"error": "You have already applied for this job."}), 409
        return jsonify({"application": {
            "id": str(result.inserted_id),
            "jobId": str(job["_id"]),
            "status": application["status"],
        }}), 201

    @app.get("/api/my-applications")
    @require_user("student")
    def list_my_applications():
        database = _database()
        applications = list(
            database["applications"]
            .find({"student_id": g.user["_id"]})
            .sort("created_at", -1)
            .limit(200)
        )
        jobs_by_id = {
            job["_id"]: job
            for job in database["jobs"].find({"_id": {"$in": [item["job_id"] for item in applications]}})
        }
        return jsonify({"applications": [
            {
                "id": str(application["_id"]),
                "job": {
                    "id": str(jobs_by_id[application["job_id"]]["_id"]),
                    "title": jobs_by_id[application["job_id"]]["title"],
                    "company": jobs_by_id[application["job_id"]]["company"],
                },
                "status": application["status"],
                "createdAt": application["created_at"].isoformat(),
            }
            for application in applications
            if application["job_id"] in jobs_by_id
        ]})

    @app.get("/api/jobs/<job_id>/applications")
    @require_user("recruiter")
    def list_job_applications(job_id):
        if not ObjectId.is_valid(job_id):
            return jsonify({"error": "Job not found."}), 404
        database = _database()
        job = database["jobs"].find_one({"_id": ObjectId(job_id), "recruiter_id": g.user["_id"]})
        if job is None:
            return jsonify({"error": "Job not found."}), 404
        applications = list(database["applications"].find({"job_id": job["_id"]}).sort("created_at", -1))
        users = {
            user["_id"]: user
            for user in database["users"].find({"_id": {"$in": [item["student_id"] for item in applications]}})
        }
        return jsonify({"applications": [
            {
                "id": str(application["_id"]),
                "student": {
                    "id": str(users[application["student_id"]]["_id"]),
                    "name": users[application["student_id"]]["name"],
                    "email": users[application["student_id"]]["email"],
                },
                "status": application["status"],
                "createdAt": application["created_at"].isoformat(),
            }
            for application in applications
            if application["student_id"] in users
        ]})

    @app.patch("/api/applications/<application_id>")
    @require_user("recruiter")
    def update_application_status(application_id):
        if not ObjectId.is_valid(application_id):
            return jsonify({"error": "Application not found."}), 404
        body, error = _json_body()
        if error:
            return error
        status = body.get("status")
        if not isinstance(status, str) or status not in {"reviewing", "shortlisted", "rejected", "hired"}:
            return jsonify({"error": "Choose reviewing, shortlisted, rejected, or hired."}), 400
        database = _database()
        application = database["applications"].find_one({"_id": ObjectId(application_id)})
        if application is None:
            return jsonify({"error": "Application not found."}), 404
        job = database["jobs"].find_one({"_id": application["job_id"], "recruiter_id": g.user["_id"]})
        if job is None:
            return jsonify({"error": "Application not found."}), 404
        database["applications"].update_one(
            {"_id": application["_id"]},
            {"$set": {"status": status, "updated_at": _utc_now()}},
        )
        return jsonify({"application": {"id": application_id, "status": status}})

    @app.post("/api/test-cases/generate")
    @require_user()
    def generate_test_cases():
        body, error = _json_body()
        if error:
            return error
        requirement = body.get("requirement")
        if not isinstance(requirement, str) or not requirement.strip() or len(requirement) > 2000:
            return jsonify({"error": "Requirement is required and must be 2,000 characters or fewer."}), 400

        normalized = requirement.strip()
        lower = normalized.lower()
        if any(word in lower for word in ("login", "sign in", "log in")):
            scenarios = [
                ("Valid login is accepted", "Submit valid student credentials.", "The authenticated student dashboard opens.", "High"),
                ("Invalid password is rejected", "Submit a registered email with an incorrect password.", "The login request is rejected without creating a session.", "High"),
                ("Missing email is validated", "Submit the login form without an email address.", "The form displays a required-field validation message.", "Medium"),
            ]
        elif "search" in lower or "filter" in lower:
            scenarios = [
                ("Matching search returns results", "Search using text from an existing job listing.", "Matching job listings are displayed.", "High"),
                ("No-match search shows an empty state", "Search using text that does not match any listing.", "A clear no-results message is displayed.", "Medium"),
                ("Empty search keeps the default listing", "Clear the search field and submit it.", "The default job listing is displayed.", "Low"),
            ]
        else:
            scenarios = [
                ("Requirement succeeds with valid data", f"Complete the workflow: {normalized}", "The requested workflow completes and the expected confirmation is shown.", "High"),
                ("Invalid input is rejected", "Repeat the workflow with a required field missing or malformed.", "The application rejects invalid input and explains the validation error.", "High"),
                ("Boundary input is handled safely", "Submit the shortest, longest, and empty values allowed by the requirement.", "The application enforces documented input boundaries without crashing.", "Medium"),
            ]

        database = _database()
        test_cases = []
        for title, scenario, expected, priority in scenarios:
            case = {
                "title": title,
                "scenario": scenario,
                "preconditions": ["HireTest Jobs application is available."],
                "steps": [scenario],
                "expected_result": expected,
                "priority": priority,
                "test_type": "functional",
                "test_data": {},
                "automation_status": "template_available",
                "approved": False,
                "created_by": g.user["_id"],
                "created_at": _utc_now(),
            }
            result = database["test_cases"].insert_one(case)
            test_cases.append({
                "id": str(result.inserted_id),
                "title": title,
                "scenario": scenario,
                "expectedResult": expected,
                "priority": priority,
                "approved": False,
            })
        return jsonify({"generator": "rule-based", "testCases": test_cases}), 201

    @app.get("/api/test-cases")
    @require_user()
    def list_test_cases():
        cases = list(_database()["test_cases"].find({"created_by": g.user["_id"]}).sort("created_at", -1).limit(200))
        return jsonify({"testCases": [
            {
                "id": str(case["_id"]),
                "title": case["title"],
                "scenario": case["scenario"],
                "expectedResult": case["expected_result"],
                "priority": case["priority"],
                "approved": case["approved"],
            }
            for case in cases
        ]})

    @app.errorhandler(ConfigurationError)
    def configuration_error(error):
        return jsonify({"error": str(error)}), 503

    @app.errorhandler(500)
    def internal_error(error):
        current_app.logger.error("Unhandled HireTest API error: %s", error)
        return jsonify({"error": "An unexpected server error occurred."}), 500

    frontend_dir = Path(app.config["FRONTEND_DIST_DIR"])

    @app.get("/")
    def frontend_index():
        if (frontend_dir / "index.html").is_file():
            return send_from_directory(frontend_dir, "index.html")
        return jsonify({"message": "HireTest AI API is running. Build the frontend to serve the application."})

    @app.get("/<path:asset_path>")
    def frontend_assets(asset_path):
        if asset_path.startswith("api/") or asset_path.startswith("socket.io/"):
            return jsonify({"error": "The requested resource was not found."}), 404
        requested = frontend_dir / asset_path
        if requested.is_file():
            return send_from_directory(frontend_dir, asset_path)
        if (frontend_dir / "index.html").is_file():
            return send_from_directory(frontend_dir, "index.html")
        return jsonify({"error": "Frontend files are not available."}), 404

    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        allow_unsafe_werkzeug=True,
    )
