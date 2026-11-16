import base64
import hashlib
import hmac
import time

from app import core
from app.ice import TURN_TTL_SECONDS, ice_configuration
from app.main import app
from fastapi.testclient import TestClient


def test_disabled_ice_has_no_third_party_stun(monkeypatch):
    monkeypatch.delenv("FAMICOM_TURN_ENABLED", raising=False)
    assert ice_configuration("owner") == {
        "enabled": False, "iceServers": [], "expires_at": None
    }


def test_turn_credential_matches_coturn_shared_secret(monkeypatch, sandbox):
    key = "fixture-only-private-secret-" + "4" * 40
    fixture = sandbox / "turn-key"
    fixture.write_text(key)
    monkeypatch.setenv("FAMICOM_TURN_ENABLED", "true")
    monkeypatch.setenv("FAMICOM_TURN_HOST", "turn.family.example.org")
    monkeypatch.setenv("FAMICOM_TURN_SECRET_FILE", str(fixture))
    result = ice_configuration("child123")
    assert result["enabled"]
    assert 0 < result["expires_at"] - int(time.time()) <= TURN_TTL_SECONDS
    server = result["iceServers"][1]
    assert server["urls"] == [
        "turn:turn.family.example.org:3478?transport=udp",
        "turn:turn.family.example.org:3478?transport=tcp",
    ]
    assert server["username"].endswith(":child123")
    expected = base64.b64encode(
        hmac.new(key.encode(), server["username"].encode(), hashlib.sha1).digest()
    ).decode()
    assert server["credential"] == expected
    assert key not in repr(result)


def test_ice_endpoint_rejects_unauthenticated_and_no_cache(monkeypatch, sandbox):
    core.create_user("parent", "Parent", "admin", "long-parent-password", "1200")
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/telephony/ice").status_code == 401
        client.post("/api/auth/login", json={"username":"parent","password":"long-parent-password"})
        disabled = client.get("/api/telephony/ice")
        assert disabled.status_code == 200
        assert disabled.headers["cache-control"] == "private, no-store, max-age=0"
        assert disabled.json()["iceServers"] == []
        monkeypatch.setenv("FAMICOM_TURN_ENABLED", "true")
        monkeypatch.setenv("FAMICOM_TURN_HOST", "turn.family.example.org")
        # Enabled without the Docker secret must fail closed, not expose public TURN.
        missing = client.get("/api/telephony/ice")
        assert missing.status_code == 503
        key = sandbox / "turn-key"
        key.write_text("another-private-turn-key-" + "9" * 40)
        monkeypatch.setenv("FAMICOM_TURN_SECRET_FILE", str(key))
        ready = client.get("/api/telephony/ice")
        assert ready.status_code == 200
        assert ready.json()["iceServers"][1]["username"].endswith(":parent")
        assert "no-store" in ready.headers["cache-control"]


def test_turn_host_rejects_url_injection(monkeypatch,sandbox):
    key = sandbox / "turn-key"
    key.write_text("fixture-" + "8" * 40)
    monkeypatch.setenv("FAMICOM_TURN_SECRET_FILE", str(key))
    monkeypatch.setenv("FAMICOM_TURN_ENABLED", "true")
    for host in ("turn.example.org/path", "https://turn.example.org", "turn:evil",
                 "turn.example.org\nfoo", "localhost", "127.0.0.1;evil"):
        monkeypatch.setenv("FAMICOM_TURN_HOST", host)
        try:
            ice_configuration("parent")
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"Host injection accepted: {host!r}")
