import os
import tempfile
from pathlib import Path

import pytest

@pytest.fixture
def sandbox(monkeypatch):
    from cryptography.fernet import Fernet
    path = Path(tempfile.mkdtemp())
    key = path / "fernet"
    key.write_bytes(Fernet.generate_key())
    monkeypatch.setenv("FAMICOM_DB_KEY_FILE", str(key))
    import app.core as core
    import app.provision as provision
    monkeypatch.setattr(core, "DB_PATH", path / "db.sqlite3")
    monkeypatch.setattr(core, "PROVISION_DIR", path / "provision")
    monkeypatch.setattr(provision, "PROVISION_DIR", path / "provision")
    core.init_db()
    return path
