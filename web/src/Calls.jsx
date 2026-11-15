import React, { useEffect, useRef, useState } from 'react';
import { Alert, Badge, Box, Button, Card, CopyButton, Divider, Group, PasswordInput, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core';
import { IconDeviceMobile, IconPhone, IconPhoneCall, IconPhoneOff, IconPlugConnected, IconRefresh, IconShieldLock, IconMicrophone, IconMicrophoneOff, IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react';
import { api } from './api';

export default function Calls({ user, config, dialTarget, onIncoming }) {
  const instance = useRef(null);
  const audio = useRef(null);
  const [dial, setDial] = useState('');
  const [state, setState] = useState('offline');
  const [incoming, setIncoming] = useState(false);
  const [error, setError] = useState('');
  const [creds, setCreds] = useState(null);
  const [muted, setMuted] = useState(false);
  const [held, setHeld] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  useEffect(() => { if (dialTarget) setDial(dialTarget); }, [dialTarget]);
  useEffect(() => () => { const current = instance.current; instance.current = null; if (current) { current.unregister().catch(() => {}); current.disconnect().catch(() => {}); } }, []);
  async function connect() {
    setError(''); setState('verbinde');
    try {
      const c = await api('/api/telephony/credentials');
      setCreds(c);
      const { Web } = await import('sip.js');
      const server = location.origin.replace(/^http/, 'ws') + c.sip_websocket;
      const phone = new Web.SimpleUser(server, {
        aor: 'sip:' + c.extension + '@' + c.domain,
        userAgentOptions: {
          authorizationUsername: c.extension,
          authorizationPassword: c.sip_password,
          displayName: user.display_name
        },
        media: { remote: { audio: audio.current }, constraints: { audio: true, video: false } },
        delegate: {
          onCallReceived: () => { setIncoming(true); setState('eingehend'); onIncoming?.();
            if ('Notification' in window && Notification.permission === 'granted') new Notification('FamiCom – eingehender Anruf', { body: 'Deine Familie ruft an.' }); },
          onCallAnswered: () => { setIncoming(false); setMuted(false); setHeld(false); setState('im Gespräch'); },
          onCallHold: isHeld => setHeld(Boolean(isHeld)),
          onServerDisconnect: () => { setIncoming(false); setMuted(false); setHeld(false); setState('offline'); },
          onCallHangup: () => { setIncoming(false); setMuted(false); setHeld(false); setState('bereit'); },
        }
      });
      instance.current = phone;
      await phone.connect();
      await phone.register();
      setState('bereit');
    } catch (err) { setState('offline'); setError(err.message); }
  }
  async function toggleMute() {
    if (!instance.current || state !== 'im Gespräch') return;
    setActionBusy(true); setError('');
    try {
      if (muted) await instance.current.unmute();
      else await instance.current.mute();
      setMuted(!muted);
    } catch (err) { setError(err.message); }
    finally { setActionBusy(false); }
  }
  async function toggleHold() {
    if (!instance.current || state !== 'im Gespräch') return;
    setActionBusy(true); setError('');
    try {
      if (held) await instance.current.unhold();
      else await instance.current.hold();
      setHeld(!held);
    } catch (err) { setError(err.message); }
    finally { setActionBusy(false); }
  }
  async function pressDigit(digit) {
    if (state !== 'im Gespräch') { setDial(value => value + digit); return; }
    if (held || !instance.current) return;
    try { await instance.current.sendDTMF(digit); }
    catch (err) { setError('DTMF konnte nicht gesendet werden: ' + err.message); }
  }
  async function call(action) {
    setError('');
    try {
      if (!instance.current) throw new Error('Telefonie ist nicht verbunden');
      if (action === 'call') {
        if (!/^(?:[2-9][0-9]{2,4}|0[0-9]{4,18})$/.test(dial)) throw new Error('Ungültige Rufnummer');
        setState('wählt');
        await instance.current.call('sip:' + dial + '@' + config.domain);
      } else if (action === 'answer') {
        await instance.current.answer();
        setIncoming(false);
      } else {
        if (action === 'decline') await instance.current.decline();
        else await instance.current.hangup();
        setIncoming(false); setHeld(false); setMuted(false); setState('bereit');
      }
    } catch (err) { setError(err.message); setState('bereit'); }
  }
  return <Box className="page-frame">
    <Group justify="space-between" mb="xl">
      <Box><Text c="dimmed" fw={700} size="xs" tt="uppercase">Telefonzentrale</Text><Title order={2}>Anrufe</Title></Box>
      <Badge variant="light" color={state === 'bereit' ? 'teal' : state === 'offline' ? 'gray' : 'blue'}>{state}</Badge>
    </Group>
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
      <Card withBorder radius="xl" p="xl" className="surface-card">
        <Stack gap="lg" align="center">
          <ThemeIcon size={76} radius="xl" variant="gradient" gradient={{ from: 'blue', to: 'cyan' }}><IconPhone size={38}/></ThemeIcon>
          <Title order={3}>{incoming ? 'Eingehender Anruf' : 'Telefon'}</Title>
          <TextInput size="lg" w="100%" aria-label="Rufnummer" placeholder="Nebenstelle oder Telefonnummer" value={dial} onChange={e => setDial(e.currentTarget.value)}/>
          <SimpleGrid cols={3} w="min(300px, 100%)" spacing="sm">
            {['1','2','3','4','5','6','7','8','9','*','0','#'].map(n => <Button key={n} size="lg" variant="light" color="gray" radius="md" onClick={() => pressDigit(n)} disabled={state === 'im Gespräch' && held}>{n}</Button>)}
          </SimpleGrid>
          <Group justify="center" grow w="100%">
            {state === 'offline' ? <Button leftSection={<IconPlugConnected size={18}/>} onClick={connect}>Telefonie verbinden</Button> :
              incoming ? <>
                <Button color="teal" leftSection={<IconPhoneCall size={18}/>} onClick={() => call('answer')}>Annehmen</Button>
                <Button color="red" leftSection={<IconPhoneOff size={18}/>} onClick={() => call('decline')}>Ablehnen</Button>
              </> : state === 'bereit' ?
                <Button color="teal" leftSection={<IconPhoneCall size={18}/>} onClick={() => call('call')}>Anrufen</Button> :
                <Button color="red" leftSection={<IconPhoneOff size={18}/>} onClick={() => call('hangup')}>Auflegen</Button>}
          </Group>
          {state === 'im Gespräch' && <Group justify="center" gap="sm" w="100%">
            <Button variant={muted ? 'filled' : 'light'} color={muted ? 'orange' : 'gray'}
              leftSection={muted ? <IconMicrophoneOff size={18}/> : <IconMicrophone size={18}/>}
              onClick={toggleMute} loading={actionBusy} aria-pressed={muted}>
              {muted ? 'Mikrofon an' : 'Stummschalten'}
            </Button>
            <Button variant={held ? 'filled' : 'light'} color={held ? 'orange' : 'gray'}
              leftSection={held ? <IconPlayerPlay size={18}/> : <IconPlayerPause size={18}/>}
              onClick={toggleHold} loading={actionBusy} aria-pressed={held}>
              {held ? 'Fortsetzen' : 'Halten'}
            </Button>
            <Text size="xs" c="dimmed" w="100%" ta="center">
              {held ? 'Gespräch gehalten – DTMF pausiert' : 'Tastenfeld sendet während des Gesprächs DTMF-Signale'}
            </Text>
          </Group>}
          <audio ref={audio} autoPlay playsInline />
          {error && <Alert color="red" w="100%">{error}</Alert>}
        </Stack>
      </Card>
      <Stack gap="md">
        <Card radius="xl" withBorder p="xl" className="surface-card">
          <Group mb="sm"><ThemeIcon variant="light"><IconDeviceMobile/></ThemeIcon><Title order={4}>Deine Nebenstelle</Title></Group>
          <Text size="xl" fw={800}>{user.extension}</Text>
          <Text size="sm" c="dimmed">Wähle andere Familienmitglieder über ihre Nebenstelle. Auch native SIP-Apps sind möglich.</Text>
          {creds && <>
            <Divider my="md"/>
            <Text size="sm"><b>SIP-Server:</b> {creds.domain}:5060</Text>
            <Text size="sm"><b>Benutzer:</b> {creds.extension}</Text>
            <CopyButton value={creds.sip_password} timeout={2000}>
              {({ copied, copy }) => <Button mt="md" variant="light" color="gray" onClick={copy}>{copied ? 'Kopiert' : 'SIP-Passwort kopieren'}</Button>}
            </CopyButton>
          </>}
        </Card>
        <Alert icon={<IconShieldLock size={18}/>} color="blue" variant="light" title="Sichere Erreichbarkeit">
          Für Browser-Anrufe wird HTTPS/WSS benötigt. Das native SIP-Protokoll ist standardmäßig nur lokal freigegeben. Externe Anrufe bleiben bis zur Freigabe eines SIP-Providers gesperrt.
        </Alert>
      </Stack>
    </SimpleGrid>
  </Box>;
}
