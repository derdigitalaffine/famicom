#!/usr/bin/env bash
# FamiCom interactive bootstrap - no docker.sock mounts, no credentials on argv.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."

dialog_input() {
  local title="$1" default="$2" result
  if command -v whiptail >/dev/null 2>&1; then
    result=$(whiptail --title "FamiCom · Einrichtung" --inputbox "$title" 9 76 "$default" 3>&1 1>&2 2>&3) || exit 1
    printf '%s' "$result"
  else
    read -r -p "$title [$default]: " result
    printf '%s' "${result:-$default}"
  fi
}
dialog_password() {
  local prompt="$1" result
  if command -v whiptail >/dev/null 2>&1; then
    result=$(whiptail --title "FamiCom · Geheimnis" --passwordbox "$prompt" 9 76 3>&1 1>&2 2>&3) || exit 1
  else
    read -r -s -p "$prompt: " result; echo >&2
  fi
  printf '%s' "$result"
}
dialog_mode() {
  if command -v whiptail >/dev/null 2>&1; then
    whiptail --title "FamiCom · HTTPS" --menu "Welche TLS-Variante verwendest du?" 15 78 3 \
      internal "Caddy-interne CA für lokale Tests / VPN" \
      public "Let's Encrypt: öffentliche Domain, DNS und Port 80/443" 3>&1 1>&2 2>&3
  else
    printf 'internal'
  fi
}
check() { command -v "$1" >/dev/null || { printf 'Fehlt: %s\n' "$1" >&2; exit 1; }; }
check docker
check openssl
check python3
docker compose version >/dev/null || { echo "Docker Compose v2 erforderlich" >&2; exit 1; }
if [[ -f .env ]]; then
  echo "Eine bestehende .env wird nicht überschrieben. Für Updates docker compose up -d --build verwenden."
  exit 0
fi

echo 'FamiCom – XMPP · FreeSWITCH · React PWA'
echo 'Empfehlung: zuerst nur lokal/VPN betreiben. Öffentliches SIP niemals ungefiltert veröffentlichen.'
domain=$(dialog_input 'XMPP-Domain (z.B. family.example.net)' 'family.example.net')
web_domain=$(dialog_input 'HTTPS-Webdomain' "chat.$domain")
admin=$(dialog_input 'Administratorkonto (kleinbuchstaben, 3–32)' 'admin')
admin_name=$(dialog_input 'Anzeigename des Administrators' 'Familienadmin')
mode=$(dialog_mode)
sip_bind=$(dialog_input 'SIP-Bind-IP: 127.0.0.1 (sicher) oder VPN/LAN-Adresse' '127.0.0.1')
public_ip=$(dialog_input 'Öffentliche SIP/RTP-Adresse: auto-nat oder festes IPv4' 'auto-nat')
admin_pw=$(dialog_password 'Administratorkennwort (min. 12 Zeichen)')
[[ "${#admin_pw}" -ge 12 ]] || { echo 'Kennwort zu kurz' >&2; exit 1; }
[[ "$domain" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ && "$web_domain" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || { echo 'Domains müssen gültige lowercase DNS-Namen sein' >&2; exit 1; }
[[ "$admin" =~ ^[a-z][a-z0-9_]{2,31}$ ]] || { echo 'Ungültiger Benutzername' >&2; exit 1; }
[[ "$admin_name" != *[\"\<\>\&]* ]] || { echo 'Anzeigename enthält ungültige Zeichen' >&2; exit 1; }
[[ "$sip_bind" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo 'Bitte IPv4-Bind-Adresse angeben' >&2; exit 1; }
[[ "$public_ip" == auto-nat || "$public_ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo 'Bitte IPv4 oder auto-nat angeben' >&2; exit 1; }
[[ "$mode" == internal || "$mode" == public ]] || exit 1

mkdir -p .secrets deploy/generated/prosody deploy/generated/freeswitch/{directory/default,dialplan/default,sip_profiles/external}
chmod 700 .secrets deploy/generated
printf 'famicom:%s\n' "$(openssl rand -hex 32)" > .secrets/xmpp_http
openssl rand -hex 32 > .secrets/esl
python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())' > .secrets/db_key
openssl req -x509 -newkey rsa:3072 -nodes -days 30 -subj "/CN=$domain" \
  -addext "subjectAltName=DNS:$domain,DNS:conference.$domain" \
  -keyout .secrets/xmpp_tls_key -out .secrets/xmpp_tls_cert >/dev/null 2>&1
chmod 600 .secrets/*
esl=$(cat .secrets/esl)
xmpp_auth=$(cat .secrets/xmpp_http)
cat > .env <<EOF
FAMICOM_DOMAIN=$domain
FAMICOM_WEB_DOMAIN=$web_domain
FAMICOM_SIP_BIND=$sip_bind
FAMICOM_SIP_PUBLIC_IP=$public_ip
FAMICOM_HTTPS_PORT=443
FAMICOM_HTTP_PORT=80
FAMICOM_TLS_MODE=$mode
FAMICOM_SECURE_COOKIES=true
FAMICOM_FREESWITCH_IMAGE=yukiosaka/freeswitch:latest
EOF
chmod 600 .env

cat > deploy/generated/prosody/famicom.cfg.lua <<EOF
-- Generated; do not edit by hand.
allow_registration = false
c2s_require_encryption = true
ssl = { key = "/run/secrets/xmpp_tls_key"; certificate = "/run/secrets/xmpp_tls_cert" }
s2s_require_encryption = true
http_ports = { 5280 }
http_interfaces = { "*" }
http_external_url = "https://$web_domain"
VirtualHost "$domain"
  authentication = "http"
  http_auth_url = "http://api:8000/internal/xmpp"
  http_auth_credentials = FileLine("/run/secrets/xmpp_http")
  modules_enabled = { "roster", "saslauth", "tls", "disco", "carbons", "smacks",
    "mam", "ping", "blocklist", "pep", "vcard4", "bosh", "websocket", "limits",
    "csi_simple", "http_file_share" }
Component "conference.$domain" "muc"
  modules_enabled = { "muc_mam" }
EOF
chmod 755 deploy/generated deploy/generated/prosody
chmod 644 deploy/generated/prosody/famicom.cfg.lua
cat > deploy/generated/Caddyfile <<EOF
$web_domain {
  $( [[ "$mode" == internal ]] && printf 'tls internal' || : )
  encode zstd gzip
  header {
    X-Content-Type-Options nosniff
    Referrer-Policy strict-origin-when-cross-origin
    X-Frame-Options DENY
  }
  handle /api/* {
    reverse_proxy api:8000
  }
  handle /xmpp-websocket* {
    reverse_proxy xmpp:5280 {
      header_up Host $domain
    }
  }
  handle /http-bind* {
    reverse_proxy xmpp:5280 {
      header_up Host $domain
    }
  }
  handle /file_share* {
    reverse_proxy xmpp:5280 {
      header_up Host $domain
    }
  }
  handle_path /sip-ws* {
    reverse_proxy freeswitch:5066
  }
  handle {
    root * /srv
    try_files {path} /index.html
    file_server
  }
}
EOF

cat > deploy/generated/freeswitch/vars.xml <<EOF
<include>
  <X-PRE-PROCESS cmd="set" data="domain=$domain"/>
  <X-PRE-PROCESS cmd="set" data="domain_name=$domain"/>
  <X-PRE-PROCESS cmd="set" data="internal_sip_port=5060"/>
  <X-PRE-PROCESS cmd="set" data="external_sip_port=5080"/>
  <X-PRE-PROCESS cmd="set" data="external_sip_ip=$public_ip"/>
  <X-PRE-PROCESS cmd="set" data="external_rtp_ip=$public_ip"/>
  <X-PRE-PROCESS cmd="set" data="global_codec_prefs=OPUS,PCMU,PCMA,VP8,H264"/>
  <X-PRE-PROCESS cmd="set" data="outbound_codec_prefs=OPUS,PCMU,PCMA"/>
  <X-PRE-PROCESS cmd="set" data="hold_music=local_stream://moh"/>
</include>
EOF
cat > deploy/generated/freeswitch/event_socket.conf.xml <<EOF
<configuration name="event_socket.conf" description="Authenticated private event socket">
  <settings>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="$esl"/>
  </settings>
</configuration>
EOF
cat > deploy/generated/freeswitch/switch.conf.xml <<'EOF'
<configuration name="switch.conf" description="FamiCom RTP limits">
  <settings>
    <param name="rtp-start-port" value="20000"/>
    <param name="rtp-end-port" value="20199"/>
    <param name="max-sessions" value="100"/>
  </settings>
</configuration>
EOF
cat > deploy/generated/freeswitch/directory/default.xml <<EOF
<include>
  <domain name="$domain">
    <params>
      <param name="dial-string" value="{presence_id=\${dialed_user}@\${dialed_domain}}sofia/internal/\${dialed_user}@\${dialed_domain}"/>
    </params>
    <groups>
      <group name="default"><users>
        <X-PRE-PROCESS cmd="include" data="directory/default/*.xml"/>
      </users></group>
    </groups>
  </domain>
</include>
EOF
cat > deploy/generated/freeswitch/dialplan/default.xml <<'EOF'
<include>
  <context name="default">
    <X-PRE-PROCESS cmd="include" data="dialplan/default/*.xml"/>
  </context>
</include>
EOF
cat > deploy/generated/freeswitch/dialplan/default/10-internal.xml <<EOF
<include>
  <extension name="family-extension">
    <condition field="destination_number" expression="^([2-9][0-9]{2,4})\$">
      <action application="set" data="hangup_after_bridge=true"/>
      <action application="bridge" data="user/\$1@$domain"/>
    </condition>
  </extension>
</include>
EOF
cat > deploy/generated/freeswitch/dialplan/default/20-features.xml <<'EOF'
<include>
  <extension name="family-conference">
    <condition field="destination_number" expression="^8([0-9]{3})$">
      <action application="answer"/>
      <action application="conference" data="$1@default"/>
    </condition>
  </extension>
  <extension name="family-voicemail">
    <condition field="destination_number" expression="^\*97$">
      <action application="answer"/>
      <action application="voicemail" data="check default ${domain_name} ${caller_id_number}"/>
    </condition>
  </extension>
</include>
EOF
cat > deploy/generated/freeswitch/dialplan/public.xml <<'EOF'
<include>
  <context name="public">
    <extension name="deny-unconfigured-inbound">
      <condition><action application="respond" data="403 Calls not configured"/></condition>
    </extension>
  </context>
</include>
EOF
cat > deploy/generated/freeswitch/sip_profiles/internal.xml <<EOF
<profile name="internal">
  <aliases/>
  <gateways/>
  <domains><domain name="all" alias="true" parse="true"/></domains>
  <settings>
    <param name="sip-ip" value="\$\${local_ip_v4}"/>
    <param name="rtp-ip" value="\$\${local_ip_v4}"/>
    <param name="ext-sip-ip" value="$public_ip"/>
    <param name="ext-rtp-ip" value="$public_ip"/>
    <param name="sip-port" value="5060"/>
    <param name="ws-binding" value=":5066"/>
    <param name="dialplan" value="XML"/>
    <param name="context" value="public"/>
    <param name="auth-calls" value="true"/>
    <param name="inbound-reg-force-matching-username" value="true"/>
    <param name="aggressive-nat-detection" value="true"/>
    <param name="manage-presence" value="true"/>
    <param name="inbound-codec-prefs" value="OPUS,PCMU,PCMA,VP8,H264"/>
    <param name="outbound-codec-prefs" value="OPUS,PCMU,PCMA,VP8,H264"/>
    <param name="rtp-timeout-sec" value="60"/>
  </settings>
</profile>
EOF
cat > deploy/generated/freeswitch/sip_profiles/external.xml <<'EOF'
<profile name="external">
  <aliases/>
  <gateways><X-PRE-PROCESS cmd="include" data="sip_profiles/external/*.xml"/></gateways>
  <domains><domain name="all" alias="false" parse="false"/></domains>
  <settings>
    <param name="sip-ip" value="$${local_ip_v4}"/>
    <param name="rtp-ip" value="$${local_ip_v4}"/>
    <param name="sip-port" value="5080"/>
    <param name="dialplan" value="XML"/>
    <param name="context" value="public"/>
    <param name="auth-calls" value="false"/>
  </settings>
</profile>
EOF
printf '<include/>\n' > deploy/generated/freeswitch/sip_profiles/external/famicom.xml
printf '<include/>\n' > deploy/generated/freeswitch/dialplan/default/30-outbound.xml
# API writes generated XML as unprivileged uid 10001; FreeSWITCH only reads it.
echo 'Starte FamiCom (Image-Build und Netzwerkzugriff erforderlich) ...'
docker compose config --quiet
docker compose up -d --build
printf '%s\n' "$admin_pw" | docker compose exec -T api python -m app.cli init-admin "$admin" "$admin_name"
unset admin_pw xmpp_auth esl
echo "Setup angelegt: https://$web_domain"
echo "Status: docker compose ps"
echo "Logs: docker compose logs -f --tail=100"
echo "WICHTIG: Initiale Zertifikate/SIP-NAT, XMPP- und SIP-Clientanrufe vor Internetfreigabe testen."
