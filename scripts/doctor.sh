#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo "Bitte zunächst ./scripts/bootstrap.sh starten" >&2; exit 1; }
echo "=== Docker Compose ==="
docker compose config --quiet
docker compose ps
echo "=== API ==="
docker compose exec -T api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=5).read().decode())"
echo "=== FreeSWITCH ==="
docker compose exec -T freeswitch fs_cli -p "$(cat .secrets/esl)" -x 'status' || true
docker compose exec -T freeswitch fs_cli -p "$(cat .secrets/esl)" -x 'sofia status' || true
echo "=== XMPP ==="
docker compose exec -T xmpp prosodyctl check config || true
echo "=== Warnungen ==="
echo "SIP/VoIP-RTP und externe XMPP-TLS-Trust-Kette sind unabhängig vom HTTPS-Proxy zu prüfen."
