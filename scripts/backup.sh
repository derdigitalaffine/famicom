#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
target="${1:?Usage: scripts/backup.sh /safe/backup/directory}"
mkdir -p "$target"
chmod 700 "$target"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
# Stop for an application-consistent multi-volume snapshot, including XMPP MAM.
docker compose stop api xmpp freeswitch
cleanup() { docker compose start api xmpp freeswitch; }
trap cleanup EXIT
docker run --rm -v famicom_famicom-data:/source:ro -v "$target":/dest alpine:3.21 sh -c "tar -C /source -czf /dest/famicom-db-$stamp.tgz ."
docker run --rm -v famicom_prosody-data:/source:ro -v "$target":/dest alpine:3.21 sh -c "tar -C /source -czf /dest/famicom-xmpp-$stamp.tgz ."
tar -czf "$target/famicom-config-$stamp.tgz" .env .secrets deploy/generated
chmod 600 "$target"/*.tgz
echo "Backup in $target abgeschlossen. Niemals unverschlüsselt extern speichern."
