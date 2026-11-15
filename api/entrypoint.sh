#!/bin/sh
set -eu
install -d -o famicom -g famicom -m 0750 /data
install -d -o famicom -g famicom -m 0750 /provision
chown -R famicom:famicom /data /provision
exec gosu famicom "$@"
