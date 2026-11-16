#!/bin/sh
# This entrypoint does not expose the shared TURN secret through argv or logs.
set -eu
umask 077
secret_path=/run/secrets/turn_rest
[ -r "$secret_path" ] || { echo 'Missing TURN shared secret' >&2; exit 1; }
secret=$(tr -d '\r\n' < "$secret_path")
case "$secret" in ''|*[!0-9a-f]*) echo 'Invalid TURN shared secret encoding' >&2; exit 1;; esac
[ "${#secret}" -ge 64 ] || { echo 'TURN shared secret is too short' >&2; exit 1; }
domain=${FAMICOM_DOMAIN:-}
printf '%s\n' "$domain" | grep -Eq '^[a-z0-9-]+(\.[a-z0-9-]+)+$' ||
  { echo 'Invalid TURN realm' >&2; exit 1; }
ip=${FAMICOM_TURN_ADVERTISE_IP:-}
if [ -n "$ip" ]; then
  printf '%s\n' "$ip" | awk -F. '
    NF!=4 {exit 1}
    {for(i=1;i<=4;i++)if($i !~ /^[0-9]+$/ || length($i)>3 || $i>255)exit 1}' ||
    { echo 'Invalid TURN advertised IPv4' >&2; exit 1; }
fi
cfg=/run/famicom-turn/turnserver.conf
cat > "$cfg" <<EOF
# Volatile and restricted; do not copy into backups or logs.
listening-port=3478
realm=$domain
fingerprint
use-auth-secret
no-tls
no-dtls
no-cli
no-loopback-peers
no-multicast-peers
min-port=49160
max-port=49179
user-quota=6
total-quota=50
stale-nonce
no-rfc5780
log-file=stdout
simple-log
EOF
if [ -n "$ip" ]; then printf 'external-ip=%s\n' "$ip" >> "$cfg"; fi
printf 'static-auth-secret=%s\n' "$secret" >> "$cfg"
unset secret
chmod 0600 "$cfg"
exec turnserver -c "$cfg"
