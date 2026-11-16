#!/bin/sh
set -eu
install -d -o famicom -g famicom -m 0750 /data
install -d -o famicom -g famicom -m 0750 /provision
chown -R famicom:famicom /data /provision
# API-generated PBX XML is owner writable and group readable. Every parent
# must allow traversal by the FreeSWITCH container's supplemental read group.
find /provision -type d -exec chmod 0750 {} +
exec gosu famicom "$@"
