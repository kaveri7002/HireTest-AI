import mongomock
import pytest
import socket
import threading
import time

from backend.app import create_app
from werkzeug.serving import make_server


@pytest.fixture
def app():
    mongo_client = mongomock.MongoClient()
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-key-not-for-production",
        "MONGO_CLIENT": mongo_client,
        "MONGODB_DATABASE": "hiretest_test",
        "FRONTEND_ORIGINS": "http://localhost:5173",
    })
    yield application
    mongo_client.close()


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def live_server(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        server.shutdown()
        raise RuntimeError("The HireTest test server did not start.")
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def student_headers(client):
    response = client.post("/api/auth/register", json={
        "name": "Student Tester",
        "email": "student@example.test",
        "password": "StrongPassword123",
        "role": "student",
    })
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json['token']}"}


@pytest.fixture
def recruiter_headers(client):
    response = client.post("/api/auth/register", json={
        "name": "Recruiter Tester",
        "email": "recruiter@example.test",
        "password": "StrongPassword123",
        "role": "recruiter",
    })
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json['token']}"}
