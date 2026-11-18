def test_health_reports_mongodb_connection(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "connected"}


def test_auth_register_login_and_role(client):
    registered = client.post("/api/auth/register", json={
        "name": "Student",
        "email": "STUDENT@example.test",
        "password": "StrongPassword123",
        "role": "student",
    })
    assert registered.status_code == 201
    assert registered.json["user"]["role"] == "student"
    assert "password" not in registered.json["user"]

    login = client.post("/api/auth/login", json={
        "email": "student@example.test",
        "password": "StrongPassword123",
    })
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json['token']}"}
    assert client.get("/api/auth/me", headers=headers).json["user"]["email"] == "student@example.test"
    assert client.post("/api/auth/register", json={
        "name": "Duplicate",
        "email": "student@example.test",
        "password": "StrongPassword123",
        "role": "student",
    }).status_code == 409


def test_job_creation_is_recruiter_only_and_listing_is_searchable(client, recruiter_headers, student_headers):
    forbidden = client.post("/api/jobs", headers=student_headers, json={
        "title": "QA Analyst",
        "company": "Example Co",
        "location": "Remote",
        "description": "Test applications.",
    })
    assert forbidden.status_code == 403

    created = client.post("/api/jobs", headers=recruiter_headers, json={
        "title": "QA Analyst",
        "company": "Example Co",
        "location": "Remote",
        "description": "Test applications.",
    })
    assert created.status_code == 201
    assert created.json["job"]["title"] == "QA Analyst"
    assert client.get("/api/jobs?search=example").json["jobs"][0]["id"] == created.json["job"]["id"]


def test_rule_based_test_cases_are_saved_for_the_tester(client, student_headers):
    generated = client.post("/api/test-cases/generate", headers=student_headers, json={
        "requirement": "Students can log in with a valid email and password.",
    })
    assert generated.status_code == 201
    assert generated.json["generator"] == "rule-based"
    assert len(generated.json["testCases"]) == 3
    assert all(not case["approved"] for case in generated.json["testCases"])

    listed = client.get("/api/test-cases", headers=student_headers)
    assert len(listed.json["testCases"]) == 3
    assert client.get("/api/dashboard", headers=student_headers).json["total"] == 0


def test_database_backed_resources_require_authentication(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/test-cases").status_code == 401
    assert client.post("/api/test-cases/generate", json={"requirement": "Login"}).status_code == 401


def test_student_can_apply_once_and_recruiter_can_update_status(client, recruiter_headers):
    created = client.post("/api/jobs", headers=recruiter_headers, json={
        "title": "QA Analyst",
        "company": "Example Co",
        "location": "Remote",
        "description": "Test applications.",
    })
    job_id = created.json["job"]["id"]
    student_response = client.post("/api/auth/register", json={
        "name": "Applicant",
        "email": "applicant@example.test",
        "password": "StrongPassword123",
        "role": "student",
    })
    student_headers = {"Authorization": f"Bearer {student_response.json['token']}"}

    applied = client.post(f"/api/jobs/{job_id}/applications", headers=student_headers)
    assert applied.status_code == 201
    application_id = applied.json["application"]["id"]
    assert client.post(f"/api/jobs/{job_id}/applications", headers=student_headers).status_code == 409

    listing = client.get(f"/api/jobs/{job_id}/applications", headers=recruiter_headers)
    assert listing.status_code == 200
    assert listing.json["applications"][0]["student"]["email"] == "applicant@example.test"
    updated = client.patch(
        f"/api/applications/{application_id}",
        headers=recruiter_headers,
        json={"status": "shortlisted"},
    )
    assert updated.status_code == 200
    my_applications = client.get("/api/my-applications", headers=student_headers)
    assert my_applications.json["applications"][0]["status"] == "shortlisted"


def test_application_routes_enforce_recruiter_ownership_and_valid_status(client, recruiter_headers):
    other_recruiter_response = client.post("/api/auth/register", json={
        "name": "Other Recruiter",
        "email": "other-recruiter@example.test",
        "password": "StrongPassword123",
        "role": "recruiter",
    })
    other_recruiter = {"Authorization": f"Bearer {other_recruiter_response.json['token']}"}
    created = client.post("/api/jobs", headers=recruiter_headers, json={
        "title": "QA Analyst",
        "company": "Example Co",
        "location": "Remote",
        "description": "Test applications.",
    })
    job_id = created.json["job"]["id"]
    student_response = client.post("/api/auth/register", json={
        "name": "Applicant",
        "email": "applicant@example.test",
        "password": "StrongPassword123",
        "role": "student",
    })
    student_headers = {"Authorization": f"Bearer {student_response.json['token']}"}
    application = client.post(f"/api/jobs/{job_id}/applications", headers=student_headers).json["application"]

    assert client.get(f"/api/jobs/{job_id}/applications", headers=student_headers).status_code == 403
    assert client.get(f"/api/jobs/{job_id}/applications", headers=other_recruiter).status_code == 404
    assert client.patch(
        f"/api/applications/{application['id']}",
        headers=other_recruiter,
        json={"status": "hired"},
    ).status_code == 404
    assert client.patch(
        f"/api/applications/{application['id']}",
        headers=recruiter_headers,
        json={"status": "unknown"},
    ).status_code == 400
