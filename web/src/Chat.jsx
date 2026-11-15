import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Group, PasswordInput, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconLock, IconMessages, IconRefresh } from '@tabler/icons-react';

let converseReady;
function loadConverse() {
  if (!converseReady) converseReady = new Promise((resolve, reject) => {
    if (window.converse) { resolve(window.converse); return; }
    const script = document.createElement('script');
    script.type = 'module';
    script.src = '/converse/converse.min.js';
    script.onload = () => window.converse ? resolve(window.converse) : reject(new Error('Converse.js konnte nicht gestartet werden'));
    script.onerror = () => reject(new Error('Chat-Modul konnte nicht geladen werden'));
    document.head.append(script);
  });
  return converseReady;
}

export default function Chat({ user, config, loginPassword }) {
  const [password, setPassword] = useState(loginPassword || '');
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const initialized = useRef(false);
  useEffect(() => {
    if (!password || initialized.current) return;
    let active = true;
    initialized.current = true;
    loadConverse().then(converse => converse.initialize({
      view_mode: 'embedded',
      websocket_url: location.origin.replace(/^http/, 'ws') + config.xmpp_websocket,
      discover_connection_methods: false,
      authentication: 'login',
      auto_login: true,
      auto_reconnect: true,
      jid: user.jid,
      password,
      locked_domain: config.domain,
      locked_muc_domain: config.group_domain,
      message_archiving: 'always',
      xhr_user_search_url: '/api/xmpp/search?',
      autocomplete_providers_url: '',
      xmpp_providers_url: '',
      show_desktop_notifications: true,
      muc_show_logs_before_join: true,
      show_send_button: true,
      allow_logout: true,
      allow_registration: false,
      assets_path: '/converse/',
      i18n: 'de',
      theme: 'concord',
    })).then(() => { if (active) { setConnected(true); setPassword(''); } })
      .catch(err => { initialized.current = false; if (active) setError(err.message); });
    return () => { active = false; };
  }, [password, user.jid, config.domain, config.group_domain, config.xmpp_websocket]);
  return (
    <Box className="chat-surface">
      {!connected && <Paper className="chat-connect" p="xl" radius="lg" withBorder>
        <Stack gap="md">
          <ThemeIcon size={58} radius="xl" variant="light"><IconMessages size={28}/></ThemeIcon>
          <Title order={2}>Deine Unterhaltungen</Title>
          <Text c="dimmed">Chats, Familiengruppen, Dateien, Lesebestätigungen und Verlauf – über deinen eigenen XMPP-Server.</Text>
          <Alert icon={<IconLock size={16}/>} color="blue" variant="light">Der Chat verbindet sich direkt mit {config.domain}. Dein Passwort wird nur im Arbeitsspeicher verwendet.</Alert>
          <PasswordInput label="XMPP-Passwort" placeholder="Passwort eingeben" autoComplete="current-password"
            value={password} onChange={e => setPassword(e.currentTarget.value)}/>
          <Group justify="space-between">
            <Text size="xs" c="dimmed">{user.jid}</Text>
            <Button onClick={() => { setError(''); initialized.current = false; setPassword(p => p || loginPassword || ''); }} disabled={!password}>Chat verbinden</Button>
          </Group>
          {error && <Alert color="red" title="Verbindung fehlgeschlagen">{error}</Alert>}
        </Stack>
      </Paper>}
      <div className="converse-container"><converse-root /></div>
    </Box>
  );
}
