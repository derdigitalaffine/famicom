#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo "Bitte zunächst ./scripts/bootstrap.sh starten" >&2; exit 1; }
echo "=== Docker Compose ==="
docker compose config --quiet
docker compose ps
echo "=== API ==="
docker compose exec -T --user 10001:10001 api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=5).read().decode())"
echo "=== FreeSWITCH ==="
docker compose exec -T freeswitch fs_cli -H freeswitch -p "$(cat .secrets/esl)" -x 'status' || echo "WARN: FreeSWITCH ESL nicht erreichbar"
docker compose exec -T freeswitch fs_cli -H freeswitch -p "$(cat .secrets/esl)" -x 'sofia status' || echo "WARN: FreeSWITCH SIP-Profile prüfen"
echo "=== XMPP ==="
docker compose exec -T xmpp prosodyctl check config || true
echo "=== Fehlgeschlagene SIP-Anmeldungen (letzte 10 Minuten) ==="
docker compose logs --no-color --since 10m freeswitch 2>/dev/null | grep -Ei 'auth failure|can.t find user|rejected' | tail -20 || true
echo "=== Warnungen ==="
echo "SIP/VoIP-RTP und externe XMPP-TLS-Trust-Kette sind unabhängig vom HTTPS-Proxy zu prüfen."
