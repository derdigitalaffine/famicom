#!/usr/bin/env bash
set -Eeuo pipefail
repo_dir=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/project/scripts" "$tmp/bin"
cp "$repo_dir/scripts/bootstrap.sh" "$tmp/project/scripts/"
cp "$repo_dir/compose.yaml" "$tmp/project/"
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
# Mock docker: this test checks generator output, NOT container availability.
exit 0
EOF
chmod +x "$tmp/bin/docker"
printf '\n\n\n\n\n\nTestSetupPasswordLong123\n' | (
  cd "$tmp/project"
  PATH="$tmp/bin:$PATH" TERM=dumb ./scripts/bootstrap.sh
)
python3 - "$tmp/project" <<'PY'
from pathlib import Path
from xml.etree import ElementTree as ET
import sys
p=Path(sys.argv[1])
conf=p/"deploy/generated/prosody/famicom.cfg.lua"
assert 'authentication = "http"' in conf.read_text()
assert 'FileLine("/run/secrets/xmpp_http")' in conf.read_text()
assert "TestSetupPasswordLong123" not in conf.read_text()
for secret in ("db_key", "xmpp_tls_key", "xmpp_tls_cert", "esl", "xmpp_http"):
    assert (p/".secrets"/secret).exists(), secret
assert len((p/".secrets/esl").read_text().strip()) >= 32
fs=p/"deploy/generated/freeswitch"
for filename in fs.rglob("*.xml"):
    ET.parse(filename)
assert 'local_ip_v4' in (fs/"sip_profiles/internal.xml").read_text()
assert 'context" value="public"' in (fs/"sip_profiles/internal.xml").read_text()
assert 'dialed_user' in (fs/"directory/default.xml").read_text()
assert 'tls internal' in (p/"deploy/generated/Caddyfile").read_text()
print("Bootstrap generator: generated secret, TLS, XMPP, FreeSWITCH configs parse")
PY
openssl x509 -in "$tmp/project/.secrets/xmpp_tls_cert" -noout -checkend 3600 >/dev/null
