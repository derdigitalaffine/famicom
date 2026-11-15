"""First-admin initialization, password never passed as command-line argument."""
import getpass
import os
import sys

from .core import create_user, database, init_db
from .provision import sync

def main():
    if len(sys.argv) < 3 or sys.argv[1] != "init-admin":
        raise SystemExit("Usage: python -m app.cli init-admin USERNAME [DISPLAY_NAME]")
    username = sys.argv[2]
    display = sys.argv[3] if len(sys.argv) > 3 else username
    init_db()
    with database() as con:
        if con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise SystemExit("A user exists; bootstrap administrator creation is locked")
    password = sys.stdin.readline().rstrip("\r\n") if not sys.stdin.isatty() else getpass.getpass("Admin password: ")
    if not password:
        raise SystemExit("An admin password is required")
    account = create_user(username, display, "admin", password, extension="1200")
    del password
    synced = sync()
    print(f"Created {account['jid']} (extension {account['extension']}); FreeSWITCH reload: {synced}")

if __name__ == "__main__":
    main()
