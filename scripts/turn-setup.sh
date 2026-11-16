#!/usr/bin/env bash
# Optional TURN installer: deliberate enable/disable, with whiptail when present.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo 'Run scripts/bootstrap.sh first' >&2; exit 1; }
command -v docker >/dev/null
command -v openssl >/dev/null
command -v python3 >/dev/null
input() {
  local prompt="$1" default="$2" result
  if [[ -t 0 ]] && command -v whiptail >/dev/null; then
    result=$(whiptail --title 'FamiCom TURN' --inputbox "$prompt" 10 78 "$default" 3>&1 1>&2 2>&3) || exit 1
  else
    read -r -p "$prompt [$default]: " result
  fi
  printf '%s' "${result:-$default}"
}
mode="${1:-enable}"
[[ "$mode" == enable || "$mode" == disable ]] || { echo 'Usage: scripts/turn-setup.sh [enable|disable]' >&2; exit 2; }
host=''
bind=''
advertise=''
if [[ "$mode" == enable ]]; then
  domain=$(sed -n 's/^FAMICOM_DOMAIN=//p' .env | head -1)
  host=$(input 'TURN host: DNS name that clients can resolve' "turn.$domain")
  bind=$(input 'Bind IP (127.0.0.1 for VPN/local, 0.0.0.0 for router port forwarding)' '127.0.0.1')
  advertise=$(input 'Public TURN IPv4 for NAT (leave empty for local-only)' '')
fi
python3 - "$mode" "$host" "$bind" "$advertise" <<'PY'
from pathlib import Path
import ipaddress, re, sys
mode, host, bind, public = sys.argv[1:]
if mode == 'enable':
    if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', host):
        raise SystemExit('Invalid TURN hostname')
    try:
        ipaddress.IPv4Address(bind)
        if public: ipaddress.IPv4Address(public)
    except ipaddress.AddressValueError as exc:
        raise SystemExit('Invalid TURN IPv4') from exc
env = Path('.env')
lines = env.read_text().splitlines()
patch = {'FAMICOM_TURN_ENABLED':'true' if mode=='enable' else 'false'}
if mode=='enable':
    patch.update(FAMICOM_TURN_HOST=host, FAMICOM_TURN_BIND=bind,
                 FAMICOM_TURN_ADVERTISE_IP=public)
for k,v in patch.items():
    hits = [i for i,row in enumerate(lines) if row.startswith(k+'=')]
    for index in reversed(hits): lines.pop(index)
    lines.append(k+'='+v)
env.write_text('\n'.join(lines)+'\n')
env.chmod(0o600)
PY
if [[ "$mode" == disable ]]; then
  docker compose --profile turn stop turn || true
  docker compose up -d api
  echo 'TURN disabled; new browsers will not receive TURN credentials.'
  exit
fi
mkdir -p .secrets
if [[ ! -s .secrets/turn_rest ]]; then
  openssl rand -hex 32 > .secrets/turn_rest
  chmod 644 .secrets/turn_rest
fi
docker compose --profile turn config --quiet
docker compose --profile turn up -d --build api turn
echo 'TURN started as an optional service.'
echo 'IMPORTANT: verify ICE relay candidates, firewall/NAT and actual two-device audio.'
if [[ "$bind" == 127.0.0.1 ]]; then
  echo 'Loopback-only binding: TURN is not accessible directly from other hosts.'
else
  echo 'Open UDP/TCP 3478 plus UDP 49160–49179 only to trusted networks as required.'
fi
