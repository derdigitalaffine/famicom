import pytest
from fastapi.testclient import TestClient
from app import core
from app.main import app

@pytest.fixture
def client(sandbox):
    with TestClient(app, base_url="https://testserver") as client:
        yield client

def login(client, name, password):
    result = client.post("/api/auth/login", json={"username": name, "password": password})
    assert result.status_code == 200
    return result.json()["csrf"]

def test_sessions_csrf_admin_and_child(client):
    core.create_user("parent", "Parent", "admin", "a-strong-admin-password", "200")
    core.create_user("child1", "Child", "child", "another-long-password", "201")
    child_csrf = login(client, "child1", "another-long-password")
    denied = client.post("/api/users", json={"username":"other1","display_name":"Other","role":"admin","password":"long-enough-secret"}, headers={"x-csrf-token": child_csrf})
    assert denied.status_code == 403
    denied = client.post("/api/auth/logout")
    assert denied.status_code == 403
    assert client.post("/api/auth/logout", headers={"x-csrf-token": child_csrf}).status_code == 200
    admin_csrf = login(client, "parent", "a-strong-admin-password")
    assert client.post("/api/users", json={"username":"other1","display_name":"Other","role":"adult","password":"long-enough-secret"}, headers={"x-csrf-token": admin_csrf}).status_code == 201

def test_http_auth_and_xml_escaping(client, sandbox, monkeypatch):
    core.create_user("person", 'A & B "<Demo>"', "adult", "secure-testing-password", "220")
    from app import provision
    provision.render_users()
    data = (sandbox / "provision/directory/default/users.xml").read_text()
    assert "&amp;" in data and "&quot;" in data and "&lt;" in data
    assert "secure-testing-password" not in data
    monkeypatch.setattr(core, "secret_file", lambda name, default="": "svc:token")
    path = "/internal/xmpp/check_password?user=person&server=family.example.org&pass=secure-testing-password"
    import base64
    auth = "Basic " + base64.b64encode(b"svc:token").decode()
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"authorization": auth}).text == "true"

def test_last_admin_protection(client):
    owner = core.create_user("owner", "Owner", "admin", "owner-long-secret-value", "200")
    csrf = login(client, "owner", "owner-long-secret-value")
    result = client.patch(f"/api/users/{owner['id']}", headers={"x-csrf-token": csrf}, json={"enabled":False})
    assert result.status_code == 409
