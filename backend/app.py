import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, current_app, g, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, join_room
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


def _notification_payload(notification):
    return {
        "id": str(notification["_id"]),
        "title": notification["title"],
        "message": notification["message"],
        "kind": notification["kind"],
        "createdAt": notification["created_at"].isoformat(),
        "read": notification.get("read", False),
        "applicationId": notification.get("application_id"),
    }


def _notify_user(database, user_id, title, message, kind, application_id=None):
    notification = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "kind": kind,
        "created_at": _utc_now(),
        "read": False,
        "application_id": application_id,
    }
    result = database["notifications"].insert_one(notification)
    notification["_id"] = result.inserted_id
    socketio.emit("notification", _notification_payload(notification), to=f"user:{user_id}")


def _job_match(job, keywords):
    searchable = f'{job["title"]} {job["description"]} {job["location"]}'.lower()
    matches = [keyword for keyword in keywords if keyword in searchable]
    return len(matches), matches


def _seed_demo_jobs(database):
    if database["jobs"].count_documents({"status": "published"}) > 0:
        return
    created_at = _utc_now()
    listings = [
        ("qa-analyst", "Junior QA Analyst", "Remote", "Review sample requirements and explore manual testing workflows."),
        ("frontend-tester", "Frontend Test Engineer", "Bengaluru, India", "Explore example browser-testing scenarios for a sample product."),
        ("software-test-intern", "Software Test Intern", "Remote", "Practice reviewing starter test cases in the HireTest demo."),
    ]
    for key, title, location, description in listings:
        database["jobs"].update_one(
            {"demo_key": key},
            {"$setOnInsert": {
                "demo_key": key,
                "is_demo": True,
                "title": title,
                "company": "HireTest Demo Studio",
                "location": location,
                "description": f"DEMO ONLY — fictional sample listing, not a real vacancy. {description}",
                "type": "Full time",
                "status": "published",
                "recruiter_id": None,
                "created_at": created_at,
            }},
            upsert=True,
        )


def _seed_starter_test_cases(database, user_id):
    if database["test_cases"].count_documents({"created_by": user_id}) > 0:
        return
    examples = [
        ("job-search-results", "Matching search returns results", "Search using text from an existing job listing.", "Matching job listings are displayed.", "High"),
        ("job-search-empty-state", "No-match search shows an empty state", "Search using text that does not match any listing.", "A clear no-results message is displayed.", "Medium"),
        ("published-job-visibility", "Published jobs appear in the jobs list", "Create and publish a job as a recruiter, then view the list as a student.", "The published job appears in the student's open roles.", "Low"),
    ]
    created_at = _utc_now()
    for key, title, scenario, expected, priority in examples:
        case = {
            "sample_key": key,
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
            "is_example": True,
            "created_by": user_id,
            "created_at": created_at,
        }
        database["test_cases"].update_one(
            {"created_by": user_id, "sample_key": key},
            {"$setOnInsert": case},
            upsert=True,
        )


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


@socketio.on("connect")
def authorize_socket(auth=None):
    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str):
        return False
    try:
        user_id = _serializer().loads(token, max_age=current_app.config["TOKEN_MAX_AGE_SECONDS"])
        user = _database()["users"].find_one({"_id": ObjectId(user_id)})
    except (BadSignature, SignatureExpired, ValueError, PyMongoError):
        return False
    if user is None:
        return False
    join_room(f"user:{user['_id']}")


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
            database["jobs"].create_index("demo_key", unique=True, sparse=True)
            database["applications"].create_index([("student_id", 1), ("job_id", 1)], unique=True)
            database["notifications"].create_index([("user_id", 1), ("created_at", -1)])
            database["test_cases"].create_index([("created_by", 1), ("created_at", -1)])
            database["test_cases"].create_index(
                [("created_by", 1), ("sample_key", 1)],
                unique=True,
                partialFilterExpression={"sample_key": {"$exists": True}},
            )
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

    @app.get("/api/profile")
    @require_user("student")
    def get_student_profile():
        return jsonify({"profile": {
            "skills": g.user.get("skills", []),
            "interests": g.user.get("interests", ""),
        }})

    @app.put("/api/profile")
    @require_user("student")
    def update_student_profile():
        body, error = _json_body()
        if error:
            return error
        skills = body.get("skills", [])
        interests = body.get("interests", "")
        if (
            not isinstance(skills, list)
            or len(skills) > 30
            or any(not isinstance(skill, str) or not skill.strip() or len(skill.strip()) > 40 for skill in skills)
        ):
            return jsonify({"error": "Enter up to 30 skills, each 40 characters or fewer."}), 400
        if not isinstance(interests, str) or len(interests.strip()) > 1000:
            return jsonify({"error": "Interests must be 1,000 characters or fewer."}), 400
        clean_skills = list(dict.fromkeys(skill.strip() for skill in skills))
        _database()["users"].update_one(
            {"_id": g.user["_id"]},
            {"$set": {"skills": clean_skills, "interests": interests.strip()}},
        )
        return jsonify({"profile": {"skills": clean_skills, "interests": interests.strip()}})

    @app.get("/api/jobs")
    def list_jobs():
        database = _database()
        _seed_demo_jobs(database)
        query = request.args.get("search", "").strip()
        filters = {"status": "published"}
        if query:
            safe_query = re.escape(query[:100])
            filters["$or"] = [
                {"title": {"$regex": safe_query, "$options": "i"}},
                {"company": {"$regex": safe_query, "$options": "i"}},
                {"location": {"$regex": safe_query, "$options": "i"}},
            ]
        jobs = list(database["jobs"].find(filters).sort("created_at", -1).limit(100))
        return jsonify({"jobs": [
            {
                "id": str(job["_id"]),
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "type": job.get("type", "Full time"),
                "description": job["description"],
                "isDemo": job.get("is_demo", False),
                "createdAt": job["created_at"].isoformat(),
            }
            for job in jobs
        ]})

    @app.get("/api/job-recommendations")
    @require_user("student")
    def recommend_jobs():
        database = _database()
        profile = database["users"].find_one(
            {"_id": g.user["_id"]},
            {"skills": 1, "interests": 1},
        ) or {}
        keywords = [
            item.lower()
            for item in (profile.get("skills", []) + re.split(r"[,;\n]+", profile.get("interests", "")))
            if isinstance(item, str) and len(item.strip()) >= 2
        ]
        keywords = list(dict.fromkeys(keywords))
        if not keywords:
            return jsonify({"recommendations": [], "message": "Add skills or interests to your profile to get job suggestions."})

        jobs = database["jobs"].find({"status": "published", "is_demo": {"$ne": True}}).limit(100)
        recommendations = []
        for job in jobs:
            match_count, matches = _job_match(job, keywords)
            if match_count == 0:
                continue
            recommendations.append({
                "job": {
                    "id": str(job["_id"]),
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "type": job.get("type", "Full time"),
                    "description": job["description"],
                    "isDemo": False,
                    "createdAt": job["created_at"].isoformat(),
                },
                "matchScore": min(100, round(100 * match_count / len(keywords))),
                "matchedSkills": matches[:5],
            })
        recommendations.sort(key=lambda item: (-item["matchScore"], item["job"]["title"].lower()))
        return jsonify({"recommendations": recommendations[:10], "message": None})

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
        job_type = body.get("type", "Full time")
        if not isinstance(job_type, str) or job_type not in {"Full time", "Part time", "Contract", "Internship"}:
            return jsonify({"error": "Choose a valid job type."}), 400
        job = {
            **fields,
            "type": job_type,
            "status": "published",
            "recruiter_id": g.user["_id"],
            "is_demo": False,
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
            "isDemo": False,
            "createdAt": job["created_at"].isoformat(),
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
            "isDemo": job.get("is_demo", False),
            "createdAt": job["created_at"].isoformat(),
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
        if job.get("is_demo"):
            return jsonify({"error": "Demo listings are for browsing only and cannot accept applications."}), 409
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return jsonify({"error": "Send application information as a JSON object."}), 400
        applicant_name = body.get("name", g.user["name"])
        applicant_email = body.get("email", g.user["email"])
        phone = body.get("phone", "")
        skills = body.get("skills", [])
        cover_letter = body.get("coverLetter", "")
        resume_url = body.get("resumeUrl", "")
        if not isinstance(applicant_name, str) or not applicant_name.strip() or len(applicant_name.strip()) > 80:
            return jsonify({"error": "Enter your name (80 characters or fewer)."}), 400
        if (
            not isinstance(applicant_email, str)
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", applicant_email.strip())
            or len(applicant_email) > 254
        ):
            return jsonify({"error": "Enter a valid contact email address."}), 400
        if not isinstance(phone, str) or len(phone) > 30 or (phone and not re.fullmatch(r"[+\d() .-]{7,30}", phone)):
            return jsonify({"error": "Enter a valid phone number or leave it blank."}), 400
        if (
            not isinstance(skills, list)
            or len(skills) > 30
            or any(not isinstance(skill, str) or not skill.strip() or len(skill.strip()) > 40 for skill in skills)
        ):
            return jsonify({"error": "Enter up to 30 skills, each 40 characters or fewer."}), 400
        if not isinstance(cover_letter, str) or len(cover_letter) > 3000:
            return jsonify({"error": "Cover note must be 3,000 characters or fewer."}), 400
        if not isinstance(resume_url, str) or len(resume_url) > 2048:
            return jsonify({"error": "Resume link must be 2,048 characters or fewer."}), 400
        if resume_url:
            parsed_resume_url = urlparse(resume_url)
            if parsed_resume_url.scheme != "https" or not parsed_resume_url.netloc:
                return jsonify({"error": "Resume link must be a valid HTTPS URL."}), 400
        application = {
            "job_id": job["_id"],
            "student_id": g.user["_id"],
            "applicant_name": applicant_name.strip(),
            "applicant_email": applicant_email.strip().lower(),
            "phone": phone.strip(),
            "skills": list(dict.fromkeys(skill.strip() for skill in skills)),
            "cover_letter": cover_letter.strip(),
            "resume_url": resume_url.strip(),
            "status": "submitted",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        try:
            result = database["applications"].insert_one(application)
        except DuplicateKeyError:
            return jsonify({"error": "You have already applied for this job."}), 409
        _notify_user(
            database,
            job["recruiter_id"],
            "New job application",
            f'{application["applicant_name"]} applied for {job["title"]}.',
            "application",
            str(result.inserted_id),
        )
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
                "interview": application.get("interview"),
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
                    "name": application.get("applicant_name", users[application["student_id"]]["name"]),
                    "email": application.get("applicant_email", users[application["student_id"]]["email"]),
                },
                "phone": application.get("phone", ""),
                "skills": application.get("skills", []),
                "coverLetter": application.get("cover_letter", ""),
                "resumeUrl": application.get("resume_url", ""),
                "status": application["status"],
                "createdAt": application["created_at"].isoformat(),
                "interview": application.get("interview"),
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
        if not isinstance(status, str) or status not in {"reviewing", "shortlisted", "interview", "rejected", "hired"}:
            return jsonify({"error": "Choose reviewing, shortlisted, interview, rejected, or hired."}), 400
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
        if application["status"] != status:
            _notify_user(
                database,
                application["student_id"],
                "Application status updated",
                f'Your application for {job["title"]} is now {status}.',
                "application_status",
                application_id,
            )
        return jsonify({"application": {"id": application_id, "status": status}})

    @app.post("/api/applications/<application_id>/interview")
    @require_user("recruiter")
    def schedule_interview(application_id):
        if not ObjectId.is_valid(application_id):
            return jsonify({"error": "Application not found."}), 404
        body, error = _json_body()
        if error:
            return error
        interview_at = body.get("scheduledAt")
        meeting_url = body.get("meetingUrl", "")
        if not isinstance(interview_at, str):
            return jsonify({"error": "Choose an interview date and time."}), 400
        try:
            scheduled_at = datetime.fromisoformat(interview_at.replace("Z", "+00:00"))
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            scheduled_at = scheduled_at.astimezone(timezone.utc)
        except ValueError:
            return jsonify({"error": "Enter a valid interview date and time."}), 400
        if scheduled_at <= _utc_now():
            return jsonify({"error": "Interview must be scheduled for a future date and time."}), 400
        if not isinstance(meeting_url, str) or len(meeting_url) > 2048:
            return jsonify({"error": "Meeting link must be 2,048 characters or fewer."}), 400
        if meeting_url:
            parsed_meeting_url = urlparse(meeting_url)
            if parsed_meeting_url.scheme != "https" or not parsed_meeting_url.netloc:
                return jsonify({"error": "Meeting link must be a valid HTTPS URL."}), 400

        database = _database()
        application = database["applications"].find_one({"_id": ObjectId(application_id)})
        if application is None:
            return jsonify({"error": "Application not found."}), 404
        job = database["jobs"].find_one({"_id": application["job_id"], "recruiter_id": g.user["_id"]})
        if job is None:
            return jsonify({"error": "Application not found."}), 404
        interview = {
            "scheduledAt": scheduled_at.isoformat(),
            "meetingUrl": meeting_url.strip(),
        }
        database["applications"].update_one(
            {"_id": application["_id"]},
            {"$set": {"interview": interview, "status": "interview", "updated_at": _utc_now()}},
        )
        local_time = scheduled_at.strftime("%b %d, %Y at %H:%M UTC")
        message = f'Your interview for {job["title"]} is scheduled for {local_time}.'
        if meeting_url:
            message += f" Meeting link: {meeting_url.strip()}"
        _notify_user(database, application["student_id"], "Interview scheduled", message, "interview", application_id)
        return jsonify({"application": {"id": application_id, "status": "interview", "interview": interview}})

    @app.get("/api/notifications")
    @require_user()
    def list_notifications():
        notifications = list(
            _database()["notifications"]
            .find({"user_id": g.user["_id"]})
            .sort("created_at", -1)
            .limit(50)
        )
        return jsonify({"notifications": [_notification_payload(item) for item in notifications]})

    @app.patch("/api/notifications/<notification_id>/read")
    @require_user()
    def mark_notification_read(notification_id):
        if not ObjectId.is_valid(notification_id):
            return jsonify({"error": "Notification not found."}), 404
        database = _database()
        result = database["notifications"].update_one(
            {"_id": ObjectId(notification_id), "user_id": g.user["_id"]},
            {"$set": {"read": True}},
        )
        if result.matched_count == 0:
            return jsonify({"error": "Notification not found."}), 404
        notification = database["notifications"].find_one({"_id": ObjectId(notification_id)})
        return jsonify({"notification": _notification_payload(notification)})

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
                "isExample": False,
            })
        return jsonify({"generator": "rule-based", "testCases": test_cases}), 201

    @app.patch("/api/test-cases/<case_id>")
    @require_user()
    def update_test_case(case_id):
        if not ObjectId.is_valid(case_id):
            return jsonify({"error": "Test case not found."}), 404
        body, error = _json_body()
        if error:
            return error

        updates = {}
        for field, limit in (("title", 160), ("scenario", 2000), ("expectedResult", 2000)):
            if field not in body:
                continue
            value = body[field]
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                return jsonify({"error": f"{field} is required and must be {limit} characters or fewer."}), 400
            updates[{"expectedResult": "expected_result"}.get(field, field)] = value.strip()
        if "priority" in body:
            if not isinstance(body["priority"], str) or body["priority"] not in {"High", "Medium", "Low"}:
                return jsonify({"error": "Choose High, Medium, or Low priority."}), 400
            updates["priority"] = body["priority"]
        if "approved" in body:
            if not isinstance(body["approved"], bool):
                return jsonify({"error": "Approval must be true or false."}), 400
            updates["approved"] = body["approved"]
        if not updates:
            return jsonify({"error": "Provide at least one test-case field to update."}), 400

        database = _database()
        case_filter = {"_id": ObjectId(case_id), "created_by": g.user["_id"]}
        result = database["test_cases"].update_one(case_filter, {"$set": updates})
        if result.matched_count == 0:
            return jsonify({"error": "Test case not found."}), 404
        case = database["test_cases"].find_one(case_filter)
        return jsonify({"testCase": {
            "id": str(case["_id"]),
            "title": case["title"],
            "scenario": case["scenario"],
            "expectedResult": case["expected_result"],
            "priority": case["priority"],
            "approved": case["approved"],
            "isExample": case.get("is_example", False),
        }})

    @app.get("/api/test-cases")
    @require_user()
    def list_test_cases():
        database = _database()
        _seed_starter_test_cases(database, g.user["_id"])
        cases = list(database["test_cases"].find({"created_by": g.user["_id"]}).sort("created_at", -1).limit(200))
        return jsonify({"testCases": [
            {
                "id": str(case["_id"]),
                "title": case["title"],
                "scenario": case["scenario"],
                "expectedResult": case["expected_result"],
                "priority": case["priority"],
                "approved": case["approved"],
                "isExample": case.get("is_example", False),
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
            response = send_from_directory(frontend_dir, "index.html")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        return jsonify({"message": "HireTest AI API is running. Build the frontend to serve the application."})

    @app.get("/<path:asset_path>")
    def frontend_assets(asset_path):
        if asset_path.startswith("api/") or asset_path.startswith("socket.io/"):
            return jsonify({"error": "The requested resource was not found."}), 404
        requested = frontend_dir / asset_path
        if requested.is_file():
            response = send_from_directory(frontend_dir, asset_path)
            if asset_path in {"sw.js", "registerSW.js"}:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response
        if (frontend_dir / "index.html").is_file():
            response = send_from_directory(frontend_dir, "index.html")
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
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
