#!/usr/bin/env bash
# Conservative in-place upgrade of an existing FamiCom installation.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo "Kein vorhandenes FamiCom gefunden; bitte scripts/bootstrap.sh verwenden." >&2; exit 1; }
command -v docker >/dev/null
command -v python3 >/dev/null
[[ -f deploy/generated/freeswitch/sip_profiles/internal.xml ]] || {
  echo "SIP-Profil fehlt; zuerst ein Backup und manuelle Diagnose durchführen." >&2; exit 1;
}
backup_destination="${FAMICOM_BACKUP_DIR:-$PWD/runtime/pre-upgrade}"
mkdir -p "$backup_destination"
chmod 700 "$backup_destination"
echo "Sichere Konfiguration und Daten vor der Umstellung ..."
./scripts/backup.sh "$backup_destination"
python3 - <<'PY'
from pathlib import Path
import os
import re
import shutil
import xml.etree.ElementTree as ET
base = Path('deploy/generated/freeswitch/sip_profiles')
env = dict(row.split('=',1) for row in Path('.env').read_text().splitlines()
           if '=' in row and not row.strip().startswith('#'))
domain=env.get('FAMICOM_DOMAIN','')
assert re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+',domain), 'Invalid family domain'
for name, settings in {
    'internal.xml': {
        'context': 'public',
        'sip-domain': domain,
        'challenge-realm': domain,
        'force-register-domain': domain,
        'force-register-db-domain': domain,
    },
    'external.xml': {'context':'famicom-provider-inbound'},
}.items():
    target = base/name
    tree=ET.parse(target)
    root=tree.getroot()
    settings_node=root.find('settings')
    if settings_node is None:
        raise SystemExit('Malformed FreeSWITCH profile: '+name)
    for key,value in settings.items():
        element = next((p for p in settings_node.findall('param') if p.get('name')==key), None)
        if element is None:
            element=ET.SubElement(settings_node,'param', name=key)
        element.set('value',value)
    temp=target.with_suffix('.xml.tmp')
    temp.write_text(ET.tostring(root,encoding='unicode')+'\n')
    os.chmod(temp,0o640)
    os.replace(temp,target)
print('Sofia profile contexts and canonical digest realm upgraded.')
PY
docker compose config --quiet
docker compose up -d --build
# A changed dialplan context does not take effect on sofia reloadxml alone.
docker compose restart freeswitch
for attempt in {1..30}; do
  if docker compose exec -T api python -c 'from app.provision import sync; assert sync()' >/dev/null 2>&1; then
    echo "FamiCom aktualisiert; Container und Nebenstellen sind neu geladen."
    echo "Hinweis: bestehende 3-stellige SIP-Nebenstellen wurden migriert. SIP-Clients auf neue 4-stellige Nummern umstellen."
    ./scripts/doctor.sh
    exit 0
  fi
  sleep 2
done
echo "FEHLER: FreeSWITCH-Provisionierung nicht bestätigt. Bitte Backup und Logs prüfen." >&2
exit 1
