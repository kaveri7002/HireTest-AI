from backend.app import create_app


def test_health_reports_mongodb_connection(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "connected"}


def test_frontend_shell_and_service_worker_disable_stale_caching(tmp_path):
    (tmp_path / "index.html").write_text("<html>latest</html>", encoding="utf-8")
    (tmp_path / "sw.js").write_text("self.skipWaiting()", encoding="utf-8")
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-key-not-for-production",
        "FRONTEND_DIST_DIR": str(tmp_path),
    })
    with application.test_client() as test_client:
        page = test_client.get("/")
        worker = test_client.get("/sw.js")

    assert page.status_code == 200
    assert "no-store" in page.headers["Cache-Control"]
    assert worker.status_code == 200
    assert "no-store" in worker.headers["Cache-Control"]


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
        "type": "Internship",
    })
    assert created.status_code == 201
    assert created.json["job"]["title"] == "QA Analyst"
    assert created.json["job"]["type"] == "Internship"
    assert "createdAt" in created.json["job"]
    listed = client.get("/api/jobs?search=example").json["jobs"]
    assert listed[0]["id"] == created.json["job"]["id"]
    assert not any(job["isDemo"] for job in listed)


def test_empty_job_board_gets_labeled_demo_listings_that_cannot_accept_applications(client, student_headers):
    first = client.get("/api/jobs")
    second = client.get("/api/jobs")

    assert first.status_code == 200
    assert len(first.json["jobs"]) == 3
    assert all(job["isDemo"] for job in first.json["jobs"])
    assert first.json["jobs"] == second.json["jobs"]
    assert all("DEMO ONLY" in job["description"] for job in first.json["jobs"])
    demo_job_id = first.json["jobs"][0]["id"]
    application = client.post(f"/api/jobs/{demo_job_id}/applications", headers=student_headers)
    assert application.status_code == 409
    assert "cannot accept applications" in application.json["error"]


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


def test_empty_test_case_workspace_gets_unapproved_starter_examples(client, student_headers):
    first = client.get("/api/test-cases", headers=student_headers)
    second = client.get("/api/test-cases", headers=student_headers)

    assert first.status_code == 200
    assert len(first.json["testCases"]) == 3
    assert first.json["testCases"] == second.json["testCases"]
    assert all(case["isExample"] and not case["approved"] for case in first.json["testCases"])
    assert client.get("/api/dashboard", headers=student_headers).json["total"] == 0


def test_test_cases_can_be_edited_and_approved_only_by_their_owner(client, student_headers):
    starter_cases = client.get("/api/test-cases", headers=student_headers).json["testCases"]
    case_id = starter_cases[0]["id"]
    updated = client.patch(f"/api/test-cases/{case_id}", headers=student_headers, json={
        "title": "Updated starter test",
        "scenario": "Run the revised sample scenario.",
        "expectedResult": "The revised expected result is shown.",
        "priority": "High",
        "approved": True,
    })
    assert updated.status_code == 200
    assert updated.json["testCase"]["title"] == "Updated starter test"
    assert updated.json["testCase"]["expectedResult"] == "The revised expected result is shown."
    assert updated.json["testCase"]["approved"] is True
    assert updated.json["testCase"]["isExample"] is True

    other_user_response = client.post("/api/auth/register", json={
        "name": "Other Student",
        "email": "other-student@example.test",
        "password": "StrongPassword123",
        "role": "student",
    })
    other_user_headers = {"Authorization": f"Bearer {other_user_response.json['token']}"}
    assert client.patch(
        f"/api/test-cases/{case_id}",
        headers=other_user_headers,
        json={"approved": False},
    ).status_code == 404
    assert client.patch(
        f"/api/test-cases/{case_id}",
        headers=student_headers,
        json={"priority": "Urgent"},
    ).status_code == 400
    assert client.patch(
        f"/api/test-cases/{case_id}",
        headers=student_headers,
        json={"priority": []},
    ).status_code == 400
    assert client.patch(
        f"/api/test-cases/{case_id}",
        headers=student_headers,
        json={"approved": "yes"},
    ).status_code == 400


def test_database_backed_resources_require_authentication(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/test-cases").status_code == 401
    assert client.post("/api/test-cases/generate", json={"requirement": "Login"}).status_code == 401
    assert client.patch("/api/test-cases/507f1f77bcf86cd799439011", json={"approved": True}).status_code == 401


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
