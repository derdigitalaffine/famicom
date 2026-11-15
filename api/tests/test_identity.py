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

def test_disabled_user_hidden_and_no_external_trunk_for_children(client, sandbox):
    from app import provision
    admin = core.create_user("owner", "Owner", "admin", "owner-long-secret-value", "200")
    child = core.create_user("child2", "Child", "child", "child-long-secret-value", "202")
    csrf = login(client, "owner", "owner-long-secret-value")
    provision.render_users()
    xml = (sandbox / "provision/directory/default/users.xml").read_text()
    assert 'name="famicom_outbound_allowed" value="false"' in xml
    assert 'name="famicom_outbound_allowed" value="true"' in xml
    assert '<user id="202">' in xml
    disabled = client.patch(f"/api/users/{child['id']}", json={"enabled":False}, headers={"x-csrf-token":csrf})
    assert disabled.status_code == 200
    assert not any(u["username"]=="child2" and u["enabled"] for u in client.get("/api/users").json())
    restored = client.patch(f"/api/users/{child['id']}", json={"enabled":True}, headers={"x-csrf-token":csrf})
    assert restored.status_code == 200
    assert any(u["username"]=="child2" and u["enabled"] for u in client.get("/api/users").json())

def test_upstream_fail_closed(client, sandbox):
    from app import provision
    user = core.create_user("parent", "Parent", "admin", "long-parent-password", "200")
    csrf = login(client, "parent", "long-parent-password")
    result = client.put("/api/admin/trunk", json={
        "enabled":True, "host":"sip.example.net", "username":"customer",
        "password":"strong-upstream-password", "allowed_prefixes":[]
    }, headers={"x-csrf-token":csrf})
    assert result.status_code == 422
    provision.render_trunk()
    assert "<include/>" in (sandbox / "provision/dialplan/default/30-outbound.xml").read_text()
    assert "<include/>" in (sandbox / "provision/sip_profiles/external/famicom.xml").read_text()
