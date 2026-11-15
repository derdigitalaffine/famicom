# FamiCom SIP migration: Foundation -> hardened PBX

**Read this before upgrading an already installed system.** Original accounts issued 3-digit internal extensions, with plaintext SIP credentials in generated FreeSWITCH directory files. The improved PBX uses 1xxx/2xxx extensions, HA1-digested secrets and an authenticated, isolated dialplan.

## In-place migration

1. Store the configured database, secret material and Prosody history in a protected, encrypted backup. The upgrade helper writes to `runtime/pre-upgrade` unless `FAMICOM_BACKUP_DIR` points to another protected folder. The helper reuses `scripts/backup.sh`, which briefly pauses services.
2. Check out the updated repository and run `./scripts/upgrade.sh`. It patches the generated Sofia internal/external profile configuration, rebuilds Compose, restarts FreeSWITCH, re-publishes XML and verifies the authenticated ESL handshake.
3. The API migrates existing 3-digit extensions. Example: old 200 becomes 1200, old 245 becomes 1245, 999 becomes 1999. Nonstandard or colliding assignments receive the next unused 1xxx/2xxx extension. Displayed XMPP usernames, passwords and chat content do not change.
4. Ask family members to update SIP client usernames/extensions and re-register. Already registered phones and active sessions can outlive an XML reload, hence the explicit FreeSWITCH restart.
5. Confirm every member can login, the SIP registration smoke passes and a test internal call routes to the intended member. Outbound provider calls remain disabled until explicitly configured and verified again.

## Rollback

Use the `runtime/pre-upgrade` snapshot created by the tool. **Do not blindly downgrade the database:** restore the pre-upgrade database, old FreeSWITCH profiles and API image together. Use a tested staging environment to practice restoring the named volumes; secrets, certificate and XMPP history must be restored as one logical unit.

## Security

The generated FreeSWITCH directory contains only SIP digest HA1, not a reusable cleartext SIP secret. HA1 is **password-equivalent for SIP digest authentication** and must still be treated as a secret (0600/0640 and volume protection). Old config archives may contain legacy plaintext material; encrypt them. The external SIP provider gateway necessarily contains its own provider credentials in restricted configuration files while enabled.
