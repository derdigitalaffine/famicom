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
    core.create_user("parent", "Parent", "admin", "a-strong-admin-password", "1200")
    core.create_user("child1", "Child", "child", "another-long-password", "1201")
    child_csrf = login(client, "child1", "another-long-password")
    denied = client.post("/api/users", json={"username":"other1","display_name":"Other","role":"admin","password":"long-enough-secret"}, headers={"x-csrf-token": child_csrf})
    assert denied.status_code == 403
    denied = client.post("/api/auth/logout")
    assert denied.status_code == 403
    assert client.post("/api/auth/logout", headers={"x-csrf-token": child_csrf}).status_code == 200
    admin_csrf = login(client, "parent", "a-strong-admin-password")
    assert client.post("/api/users", json={"username":"other1","display_name":"Other","role":"adult","password":"long-enough-secret"}, headers={"x-csrf-token": admin_csrf}).status_code == 201

def test_http_auth_and_xml_escaping(client, sandbox, monkeypatch):
    core.create_user("person", 'A & B "<Demo>"', "adult", "secure-testing-password", "1220")
    from app import provision
    provision.render_users()
    data = (sandbox / "provision/directory/default.xml").read_text()
    from xml.etree import ElementTree as ET
    root = ET.fromstring(data)
    assert root.find(".//user[@id='1220']") is not None
    assert "secure-testing-password" not in data
    assert 'name="a1-hash"' in data
    assert "A & B" not in data  # display labels are never SIP credentials
    monkeypatch.setattr(core, "secret_file", lambda name, default="": "svc:token")
    path = "/internal/xmpp/check_password?user=person&server=family.example.org&pass=secure-testing-password"
    import base64
    auth = "Basic " + base64.b64encode(b"svc:token").decode()
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"authorization": auth}).text == "true"

def test_last_admin_protection(client):
    owner = core.create_user("owner", "Owner", "admin", "owner-long-secret-value", "1200")
    csrf = login(client, "owner", "owner-long-secret-value")
    result = client.patch(f"/api/users/{owner['id']}", headers={"x-csrf-token": csrf}, json={"enabled":False})
    assert result.status_code == 409

def test_disabled_user_hidden_and_no_external_trunk_for_children(client, sandbox):
    from app import provision
    admin = core.create_user("owner", "Owner", "admin", "owner-long-secret-value", "1200")
    child = core.create_user("child2", "Child", "child", "child-long-secret-value", "1202")
    csrf = login(client, "owner", "owner-long-secret-value")
    provision.render_users()
    xml = (sandbox / "provision/directory/default.xml").read_text()
    assert 'name="outbound_allowed" value="false"' in xml
    assert 'name="outbound_allowed" value="true"' not in xml
    assert '<user id="1202">' in xml
    disabled = client.patch(f"/api/users/{child['id']}", json={"enabled":False}, headers={"x-csrf-token":csrf})
    assert disabled.status_code == 200
    assert not any(u["username"]=="child2" and u["enabled"] for u in client.get("/api/users").json())
    restored = client.patch(f"/api/users/{child['id']}", json={"enabled":True}, headers={"x-csrf-token":csrf})
    assert restored.status_code == 200
    assert any(u["username"]=="child2" and u["enabled"] for u in client.get("/api/users").json())

def test_upstream_fail_closed(client, sandbox):
    from app import provision
    user = core.create_user("parent", "Parent", "admin", "long-parent-password", "1200")
    csrf = login(client, "parent", "long-parent-password")
    result = client.put("/api/admin/trunk", json={
        "enabled":True, "host":"sip.example.net", "username":"customer",
        "password":"strong-upstream-password", "allowed_prefixes":[]
    }, headers={"x-csrf-token":csrf})
    assert result.status_code == 422
    provision.render_trunk()
    assert "sofia/gateway/" not in (sandbox / "provision/dialplan/default.xml").read_text()
    assert "gateway" not in (sandbox / "provision/sip_profiles/external/famicom.xml").read_text()

def test_contact_search_authorized_and_limited(client):
    core.create_user("parent", "Parent", "admin", "a-strong-admin-password", "1200")
    core.create_user("child1", "Child", "child", "a-strong-child-password", "1201")
    assert client.get("/api/xmpp/search?q=chi").status_code == 401
    login(client, "parent", "a-strong-admin-password")
    found = client.get("/api/xmpp/search?q=chi")
    assert found.status_code == 200
    assert found.json() == [{"jid":"child1@family.example.org","fullname":"Child"}]
    assert client.get("/api/xmpp/search?q=ch").json() == found.json()

def test_existing_three_digit_extensions_are_migrated_without_losing_user(sandbox):
    """V1 installed databases receive a predictable one-time extension migration."""
    with core.database() as db:
        db.execute(
            "INSERT INTO users(username,display_name,role,password_hash,extension,sip_secret_cipher,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("legacy", "Legacy", "adult", core.hash_password("legacy-strong-password"),
             "299", core.encrypt("RandomSipSecretOfAdequateLength"), 0)
        )
    core.init_db()
    core.init_db()  # idempotency is crucial for container restart
    with core.database() as db:
        row = db.execute("SELECT * FROM users WHERE username='legacy'").fetchone()
        migrations = db.execute("SELECT COUNT(*) FROM audit WHERE action='sip.extension.migrated'").fetchone()[0]
    assert row["extension"] == "1299"
    assert row["outbound_allowed"] == 0
    assert migrations == 1

def test_admin_outbound_permission_and_trunk_allowlist(client, sandbox):
    from app import provision
    parent = core.create_user("parent", "Parent", "admin", "strong-parent-password", "1200")
    child = core.create_user("child1", "Child", "child", "strong-child-password", "1201")
    adult = core.create_user("adult1", "Adult", "adult", "strong-adult-password", "1202")
    csrf = login(client, "parent", "strong-parent-password")
    headers = {"x-csrf-token":csrf}
    denied = client.patch(f"/api/users/{child['id']}", headers=headers, json={"outbound_allowed":True})
    assert denied.status_code == 422
    good = client.patch(f"/api/users/{adult['id']}", headers=headers, json={"outbound_allowed":True})
    assert good.status_code == 200
    assert good.json()["user"]["outbound_allowed"]
    for forbidden_prefix in ([], ["090012345"], ["0"], ["49"], ["0049631", "0049631"]):
        result = client.put("/api/admin/trunk", headers=headers, json={
            "enabled":True, "host":"sip.example.net", "username":"12345678",
            "password":"Long_ProviderPassword2026", "allowed_prefixes":forbidden_prefix
        })
        assert result.status_code == 422, forbidden_prefix
    enabled = client.put("/api/admin/trunk", headers=headers, json={
        "enabled":True, "host":"sip.example.net", "username":"12345678",
        "password":"Long_ProviderPassword2026", "allowed_prefixes":["0049631"]
    })
    assert enabled.status_code == 200
    gateway = (sandbox/"provision/sip_profiles/external/famicom.xml").read_text()
    dialplan = (sandbox/"provision/dialplan/default.xml").read_text()
    directory = (sandbox/"provision/directory/default.xml").read_text()
    assert "sofia/gateway/famicom/" in dialplan
    assert "0049631" in dialplan
    assert 'name="outbound_allowed" value="true"' in directory
    assert "Long_ProviderPassword2026" in gateway
    assert "Long_ProviderPassword2026" not in dialplan
    assert 'context name="famicom-internal"' in dialplan
    assert "sofia/gateway" not in (sandbox/"provision/dialplan/public.xml").read_text()
    disabled = client.put("/api/admin/trunk", headers=headers, json={"enabled":False})
    assert disabled.status_code == 200
    assert "sofia/gateway/" not in (sandbox/"provision/dialplan/default.xml").read_text()

def test_call_group_conference_and_child_authorization(client, sandbox):
    from app import provision
    parent = core.create_user("parent", "Parent", "admin", "strong-parent-password", "1200")
    child = core.create_user("child1", "Child", "child", "strong-child-password", "1201")
    child_csrf = login(client, "child1", "strong-child-password")
    payload = {"extension":"6001","name":"Alle zuhause","members":["1200","1201"]}
    assert client.post("/api/admin/call-groups", json=payload, headers={"x-csrf-token":child_csrf}).status_code == 403
    client.post("/api/auth/logout", headers={"x-csrf-token":child_csrf})
    csrf = login(client, "parent", "strong-parent-password")
    headers = {"x-csrf-token":csrf}
    assert client.post("/api/admin/call-groups",json=payload,headers=headers).status_code == 201
    assert client.post("/api/admin/call-groups",json={"extension":"6002","name":"Bad","members":["9999"]},headers=headers).status_code == 422
    assert client.post("/api/admin/conferences",json={"extension":"3001","name":"Familienchat"},headers=headers).status_code == 201
    overview = client.get("/api/telephony/directory").json()
    assert any(g["extension"] == "6001" for g in overview["groups"])
    assert any(c["extension"] == "3001" for c in overview["conferences"])
    dialplan = (sandbox/"provision/dialplan/default.xml").read_text()
    assert "ringgroup-6001" in dialplan
    assert "conference-3001" in dialplan
    assert client.patch(f"/api/users/{child['id']}",json={"enabled":False},headers=headers).status_code == 200
    provision.publish()
    directory = (sandbox/"provision/directory/default.xml").read_text()
    assert '<user id="1201">' not in directory
    dialplan = (sandbox/"provision/dialplan/default.xml").read_text()
    assert 'user/1201@' not in dialplan
    assert client.delete("/api/admin/call-groups/6001",headers=headers).status_code == 200


def test_runtime_xml_includes_have_no_nested_xml_declarations(sandbox):
    """FreeSWITCH preprocessor inserts fragments into its single XML document."""
    from app import provision
    core.create_user("parent", "Parent", "admin", "strong-parent-password", "1200")
    fragments = provision.configuration_xml()
    for path, contents in fragments.items():
        assert not contents.lstrip().startswith("<?xml"), path
        assert contents.lstrip().startswith("<include"), path
    assert '<user id="1200"' in fragments["directory/default.xml"]
    assert "\n  <domain " in fragments["directory/default.xml"]
    assert "famicom-internal" in fragments["dialplan/default.xml"]
