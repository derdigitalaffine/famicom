import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@mantine/core/styles.css';
import './styles.css';
import {
  ActionIcon, Alert, Avatar, Badge, Box, Button, Card, Center, Checkbox, Divider, Group,
  LoadingOverlay, MantineProvider, Modal, Notification, PasswordInput, ScrollArea, Select,
  SimpleGrid, Stack, Switch, Table, Text, TextInput, ThemeIcon, Title, createTheme
} from '@mantine/core';
import {
  IconArrowLeft, IconCheck, IconDeviceMobile, IconLogout, IconMessageCircle2, IconPhone,
  IconPlus, IconSettings, IconShieldLock, IconUserPlus, IconUsers, IconX
} from '@tabler/icons-react';
import Chat from './Chat';
import Calls from './Calls';
import PbxManagement from './PbxManagement';
import { api } from './api';

const theme = createTheme({
  primaryColor: 'blue',
  defaultRadius: 'md',
  fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: { fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontWeight: '750' },
  colors: {
    night: ['#f1f5ff','#dce7ff','#b2c8ff','#83a8ff','#4c81f5','#2363e5','#174ecc','#123da6','#0f307e','#081e50']
  }
});
const NAV = [
  { id: 'chat', title: 'Nachrichten', icon: IconMessageCircle2, subtitle: 'Privat & in Gruppen' },
  { id: 'calls', title: 'Anrufe', icon: IconPhone, subtitle: 'SIP & Telefonkonferenz' },
  { id: 'family', title: 'Familie', icon: IconUsers, subtitle: 'Mitglieder und Kontakte' },
  { id: 'settings', title: 'Verwaltung', icon: IconSettings, subtitle: 'Konten & Verbindungen' },
];

function Login({ config, onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const result = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      onLogin(result, password);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <div className="login-layout">
    <div className="login-aura login-aura-a"/><div className="login-aura login-aura-b"/>
    <Stack className="login-heading" gap="xs">
      <div className="brand-mark"><IconMessageCircle2 size={26}/></div>
      <Title order={1}>Fami<span>Com</span></Title>
      <Text size="lg" c="dimmed">Ein Ort für alle, die dir wichtig sind.</Text>
      <Group gap="xs" mt="md"><Badge color="blue" variant="light">Privat gehostet</Badge><Badge color="teal" variant="light">XMPP & VoIP</Badge><Badge color="gray" variant="light">Für deine Familie</Badge></Group>
    </Stack>
    <Card className="login-card" radius="xl" padding="xl" withBorder>
      <form onSubmit={submit}>
        <Stack gap="lg">
          <Box><Text size="xs" c="dimmed" fw={800} tt="uppercase">Schön, dass du da bist</Text><Title order={2}>Willkommen zu Hause.</Title><Text c="dimmed" mt={6}>Mit deinem Familienkonto anmelden.</Text></Box>
          <TextInput label="Benutzername" value={username} onChange={e => setUsername(e.currentTarget.value)}
            autoComplete="username" placeholder="z. B. maria" size="md" required/>
          <PasswordInput label="Passwort" value={password} onChange={e => setPassword(e.currentTarget.value)}
            autoComplete="current-password" placeholder="Dein Passwort" size="md" required/>
          {error && <Alert color="red" title="Anmeldung nicht möglich">{error}</Alert>}
          <Button type="submit" size="lg" radius="md" loading={busy}>Anmelden</Button>
          <Group gap="xs" justify="center"><IconShieldLock size={16} color="var(--mantine-color-dimmed)"/><Text size="xs" c="dimmed">{config?.domain || 'Dein eigener Server'} · Deine Daten bleiben bei dir</Text></Group>
        </Stack>
      </form>
    </Card>
    <Text className="login-foot" c="dimmed" size="xs">FamiCom · Kein externes Chat-Konto erforderlich</Text>
  </div>;
}

function Family({ user, members, onCall }) {
  const [query, setQuery] = useState('');
  const visible = members.filter(m => m.enabled && (m.display_name + ' ' + m.username + ' ' + m.extension).toLowerCase().includes(query.toLowerCase()));
  return <div className="page-frame">
    <Group justify="space-between" mb="xl"><Box><Text className="eyebrow">Miteinander verbunden</Text><Title order={2}>Deine Familie</Title></Box><Badge variant="light" size="lg">{members.length} Mitglieder</Badge></Group>
    <TextInput aria-label="Familienmitglieder suchen" placeholder="Name, Benutzername oder Nebenstelle suchen …" value={query} onChange={event => setQuery(event.currentTarget.value)} mb="lg" />
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
      {visible.map(member => <Card withBorder radius="xl" p="xl" className="surface-card member-card" key={member.id}>
        <Group align="start" wrap="nowrap">
          <Avatar size={54} radius="xl" color={member.role === 'child' ? 'grape' : member.role === 'admin' ? 'cyan' : 'blue'}>{member.display_name[0]?.toUpperCase()}</Avatar>
          <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
            <Text fw={800} truncate>{member.display_name}</Text><Text size="xs" c="dimmed" truncate>{member.jid}</Text>
            <Badge size="xs" color={member.role === 'admin' ? 'cyan' : member.role === 'child' ? 'grape' : 'gray'} variant="light">{member.role === 'admin' ? 'Administrator' : member.role === 'child' ? 'Kind' : 'Familienmitglied'}</Badge>
          </Stack>
        </Group>
        <Divider my="lg"/>
        <Group justify="space-between"><Box><Text c="dimmed" size="xs">Telefonnebenstelle</Text><Text fw={800}>{member.extension}</Text></Box><Button size="xs" color="blue" variant="light" leftSection={<IconPhone size={14}/>} onClick={() => onCall(member.extension)}>Anrufen</Button></Group>
      </Card>)}
    </SimpleGrid>
  </div>;
}

function Admin({ csrf, user, onRefresh, members }) {
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ username: '', display_name: '', password: '', role: 'adult', extension: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [trunk, setTrunk] = useState({ enabled: false, host: '', username: '', password: '', allowed_prefixes: '' });
  const [trunkLoaded, setTrunkLoaded] = useState(false);
  useEffect(() => {
    if (user.role !== 'admin') return;
    api('/api/admin/trunk').then(t => { setTrunk({ ...t, password: '', allowed_prefixes: t.allowed_prefixes.join(', ') }); setTrunkLoaded(true); }).catch(err => setError(err.message));
  }, [user.role]);
  async function createMember(e) {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api('/api/users', { method: 'POST', body: JSON.stringify({ ...form, extension: form.extension || null }) }, csrf);
      setModal(false); setForm({ username: '', display_name: '', password: '', role: 'adult', extension: '' }); await onRefresh();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  async function setOutbound(member, outbound_allowed) {
    setSaving(true); setError('');
    try {
      await api('/api/users/' + member.id, { method:'PATCH', body:JSON.stringify({ outbound_allowed }) }, csrf);
      await onRefresh();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  async function setEnabled(member, enabled) {
    setSaving(true); setError('');
    try {
      await api('/api/users/' + member.id, { method: 'PATCH', body: JSON.stringify({ enabled }) }, csrf); await onRefresh();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  async function saveTrunk(e) {
    e.preventDefault(); setSaving(true); setError('');
    try {
      await api('/api/admin/trunk', { method: 'PUT', body: JSON.stringify({
        ...trunk, allowed_prefixes: trunk.allowed_prefixes.split(',').map(v => v.trim()).filter(Boolean), password: trunk.password || null
      }) }, csrf);
      setTrunk(t => ({ ...t, password: '' }));
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  }
  return <Stack gap="xl" className="page-frame">
    <Group justify="space-between"><Box><Text className="eyebrow">Geschützter Bereich</Text><Title order={2}>Familienverwaltung</Title></Box><Button leftSection={<IconUserPlus size={18}/>} onClick={() => setModal(true)}>Mitglied anlegen</Button></Group>
    {error && <Alert color="red" withCloseButton onClose={() => setError('')}>{error}</Alert>}
    <Card radius="xl" withBorder p="xl" className="surface-card">
      <Group justify="space-between" mb="lg"><Title order={3}>Konten und Berechtigungen</Title><Badge variant="light">{members.length} aktiv</Badge></Group>
      <ScrollArea type="auto">
        <Table verticalSpacing="md" miw={620} highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Mitglied</Table.Th><Table.Th>Rolle</Table.Th><Table.Th>SIP</Table.Th><Table.Th>Extern</Table.Th><Table.Th>Aktiv</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{members.map(m => <Table.Tr key={m.id}>
            <Table.Td><Text fw={700}>{m.display_name}</Text><Text size="xs" c="dimmed">{m.username}</Text></Table.Td>
            <Table.Td><Badge variant="light" color={m.role === 'admin' ? 'blue' : m.role === 'child' ? 'grape' : 'gray'}>{m.role}</Badge></Table.Td>
            <Table.Td><Text fw={700}>{m.extension}</Text></Table.Td>
            <Table.Td><Switch checked={m.outbound_allowed} disabled={saving || m.role === 'child' || !m.enabled}
              onChange={e => setOutbound(m, e.currentTarget.checked)}
              aria-label={'Externe Telefonie für ' + m.display_name}/></Table.Td>
            <Table.Td><Switch disabled={saving || m.id === user.id} checked={m.enabled} onChange={e => setEnabled(m, e.currentTarget.checked)} aria-label={m.display_name + ' aktivieren'} /></Table.Td>
          </Table.Tr>)}</Table.Tbody>
        </Table>
      </ScrollArea>
      <Text size="xs" c="dimmed" mt="md">Deaktivierte Mitglieder werden sofort abgemeldet. Historische XMPP-Nachrichten und die Medienaufbewahrung folgen getrennten Löschregeln.</Text>
    </Card>
    <PbxManagement csrf={csrf} members={members}/>
    <Card withBorder radius="xl" p="xl" className="surface-card">
      <Group gap="sm" mb="lg"><ThemeIcon variant="light"><IconPhone size={18}/></ThemeIcon><Title order={3}>SIP-Upstream</Title><Badge variant="light" color={trunk.enabled ? 'yellow' : 'gray'}>{trunk.enabled ? 'Freigabe aktiviert' : 'Gesperrt'}</Badge></Group>
      <Alert color="orange" variant="light" mb="lg" title="Kostenpflichtige Verbindungen">Externe Telefonie ist standardmäßig deaktiviert. Freigabe nur mit geprüften Providerdaten, Rufnummernpräfixen und Kostenkontrolle. Keine Notruffunktion zugesichert.</Alert>
      <form onSubmit={saveTrunk}><Stack gap="md">
        <Switch disabled={!trunkLoaded} label="Externe Anrufe erlauben" checked={trunk.enabled} onChange={e => setTrunk(t => ({ ...t, enabled: e.currentTarget.checked }))} />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="SIP-Provider-Host" placeholder="sip.provider.example" value={trunk.host} onChange={e => setTrunk(t => ({ ...t, host: e.currentTarget.value }))}/>
          <TextInput label="Provider-Benutzername" value={trunk.username} onChange={e => setTrunk(t => ({ ...t, username: e.currentTarget.value }))}/>
        </SimpleGrid>
        <PasswordInput label="Provider-Passwort (leer = beibehalten)" value={trunk.password} onChange={e => setTrunk(t => ({ ...t, password: e.currentTarget.value }))}/>
        <TextInput label="Ausdrücklich erlaubte Nummernpräfixe" placeholder="0049631, 0049301234" description="Nur vollständige erlaubte Präfixe (führende 0, mindestens 5 Ziffern). Wählen mit 9 + Rufnummer, z. B. 9 0049631…. Premium-Nummern werden blockiert." value={trunk.allowed_prefixes} onChange={e => setTrunk(t => ({ ...t, allowed_prefixes: e.currentTarget.value }))}/>
        <Group justify="flex-end"><Button type="submit" loading={saving} disabled={!trunkLoaded}>SIP-Konfiguration speichern</Button></Group>
      </Stack></form>
    </Card>
    <Modal opened={modal} onClose={() => setModal(false)} title="Familienmitglied hinzufügen" centered radius="lg" size="md">
      <form onSubmit={createMember}><Stack gap="md">
        <TextInput label="Anzeigename" required value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.currentTarget.value }))}/>
        <TextInput label="Benutzername" description="3–32 Zeichen, Kleinbuchstaben, Ziffern, Unterstrich" required value={form.username} onChange={e => setForm(f => ({ ...f, username: e.currentTarget.value }))}/>
        <PasswordInput label="Startpasswort (mindestens 12 Zeichen)" required minLength={12} value={form.password} onChange={e => setForm(f => ({ ...f, password: e.currentTarget.value }))}/>
        <Select label="Rolle" data={[{value:'adult',label:'Erwachsenes Mitglied'},{value:'child',label:'Kind'},{value:'admin',label:'Familienadministrator'}]} value={form.role} onChange={value => setForm(f => ({ ...f, role: value || 'adult' }))}/>
        <TextInput label="SIP-Nebenstelle (optional)" placeholder="Automatisch vergeben" value={form.extension} onChange={e => setForm(f => ({ ...f, extension: e.currentTarget.value }))}/>
        {error && <Alert color="red">{error}</Alert>}
        <Button type="submit" loading={saving}>Konto hinzufügen</Button>
      </Stack></form>
    </Modal>
  </Stack>;
}

function Settings({ user, csrf, members, onRefresh, config, onSignOut }) {
  const [passwords, setPasswords] = useState({ current_password: '', new_password: '' });
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  async function changePassword(e) {
    e.preventDefault(); setError('');
    try {
      await api('/api/account/password', { method: 'POST', body: JSON.stringify(passwords) }, csrf);
      setPasswords({ current_password:'', new_password:'' });
      await onSignOut(true);
    } catch (err) { setError(err.message); }
  }
  return <Stack gap="xl" className="page-frame">
    <Box><Text className="eyebrow">Konto und Dienste</Text><Title order={2}>Einstellungen</Title></Box>
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
      <Card withBorder radius="xl" className="surface-card" p="xl">
        <Group mb="xl"><Avatar color="blue" size={58} radius="xl">{user.display_name[0]?.toUpperCase()}</Avatar><Box><Title order={4}>{user.display_name}</Title><Text c="dimmed" size="sm">{user.jid}</Text></Box></Group>
        <Stack gap="xs"><Text size="sm"><b>Rolle:</b> {user.role}</Text><Text size="sm"><b>SIP:</b> {user.extension}@{config.domain}</Text><Text size="sm"><b>Server:</b> {config.domain}</Text></Stack>
      </Card>
      <Card withBorder radius="xl" className="surface-card" p="xl">
        <Title order={4} mb="md">Passwort ändern</Title>
        <form onSubmit={changePassword}><Stack gap="sm">
          <PasswordInput label="Aktuelles Passwort" value={passwords.current_password} onChange={e => setPasswords(p => ({ ...p, current_password: e.currentTarget.value }))} required/>
          <PasswordInput label="Neues Passwort" minLength={12} value={passwords.new_password} onChange={e => setPasswords(p => ({ ...p, new_password: e.currentTarget.value }))} required/>
          {error && <Alert color="red">{error}</Alert>}
          <Button type="submit" mt="sm" variant="light">Passwort ändern</Button>
        </Stack></form>
      </Card>
    </SimpleGrid>
    <Card withBorder p="xl" radius="xl" className="surface-card">
      <Group mb="sm"><ThemeIcon variant="light"><IconDeviceMobile size={20}/></ThemeIcon><Title order={4}>Mit anderen Apps verbinden</Title></Group>
      <Text c="dimmed" size="sm">Jeder standardkonforme XMPP-Client kann dein Konto verwenden: {user.jid}. Für SIP-Apps trage die Nebenstelle {user.extension} und den SIP-Server ein. Das separate SIP-Passwort findest du unter „Anrufe“ nach der Aktivierung.</Text>
    </Card>
    {user.role === 'admin' && <Admin csrf={csrf} user={user} members={members} onRefresh={onRefresh}/>}
  </Stack>;
}

function App() {
  const [config, setConfig] = useState(null);
  const [session, setSession] = useState(null);
  const [loginPassword, setLoginPassword] = useState('');
  const [page, setPage] = useState('chat');
  const [dialTarget, setDialTarget] = useState('');
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function refreshMembers() { try { setMembers(await api('/api/users')); } catch (err) { setError(err.message); } }
  useEffect(() => {
    Promise.all([api('/api/config'), api('/api/auth/me').catch(() => null)])
      .then(([conf, sess]) => { setConfig(conf); setSession(sess); }).catch(err => setError(err.message)).finally(() => setLoading(false));
  }, []);
  useEffect(() => { if (session) refreshMembers(); else setMembers([]); }, [session?.user?.id]);
  useEffect(() => { if ('serviceWorker' in navigator && import.meta.env.PROD) navigator.serviceWorker.register('/sw.js').catch(() => {}); }, []);
  async function signOut(skipRequest = false) {
    if (!skipRequest && session) { try { await api('/api/auth/logout', { method: 'POST' }, session.csrf); } catch { /* local session still ends */ } }
    setSession(null); setLoginPassword(''); setPage('chat');
    // Converse may still be active until page reload. Clear the live JS process without caching credentials.
    window.location.reload();
  }
  if (loading) return <Center mih="100vh"><div className="loading-orbit"/><Text ml="md">FamiCom startet …</Text></Center>;
  if (!config) return <Center mih="100vh"><Alert color="red" title="Server nicht erreichbar">{error || 'Konfiguration konnte nicht geladen werden.'}</Alert></Center>;
  if (!session) return <Login config={config} onLogin={(value, plain) => { setSession(value); setLoginPassword(plain); }}/>;
  const user = session.user;
  const pages = NAV;
  return <div className="app-layout">
    <aside className="desktop-sidebar">
      <div className="side-brand"><div className="brand-mark"><IconMessageCircle2 size={22}/></div><div><b>FamiCom</b><small>Zuhause verbunden</small></div></div>
      <Text className="side-label">DEIN ZUHAUSE</Text>
      <Stack gap={7} className="side-nav">{pages.map(p => {
        const Icon = p.icon;
        return <button className={'side-link' + (page === p.id ? ' selected' : '')} onClick={() => setPage(p.id)} key={p.id}>
          <span className="side-icon"><Icon size={22}/></span><span className="side-copy"><strong>{p.title}</strong><small>{p.subtitle}</small></span>
        </button>;
      })}</Stack>
      <div className="side-footer">
        <Group gap="sm" wrap="nowrap"><Avatar radius="xl" color="blue">{user.display_name[0]?.toUpperCase()}</Avatar><div className="side-user"><Text size="sm" fw={800} truncate>{user.display_name}</Text><Text size="xs" c="dimmed" truncate>{user.username}@{config.domain}</Text></div><ActionIcon variant="subtle" color="gray" onClick={() => signOut()} aria-label="Abmelden"><IconLogout size={19}/></ActionIcon></Group>
      </div>
    </aside>
    <main className={'main-panel ' + (page === 'chat' ? 'chat-panel' : '')}>
      <div className="mobile-header"><div className="mobile-brand"><div className="brand-mark"><IconMessageCircle2 size={20}/></div><b>FamiCom</b></div><Avatar color="blue" radius="xl" size="sm">{user.display_name[0]?.toUpperCase()}</Avatar></div>
      {error && <Alert color="red" withCloseButton onClose={() => setError('')} m="md">{error}</Alert>}
      <div style={{ display: page === 'chat' ? 'block' : 'none' }} aria-hidden={page !== 'chat'}><Chat user={user} config={config} loginPassword={loginPassword}/></div>
      <div style={{ display: page === 'calls' ? 'block' : 'none' }} aria-hidden={page !== 'calls'}><Calls user={user} config={config} dialTarget={dialTarget} onIncoming={() => setPage('calls')}/></div>
      {page === 'family' && <Family user={user} members={members} onCall={extension => { setDialTarget(extension); setPage('calls'); }}/>}
      {page === 'settings' && <Settings user={user} csrf={session.csrf} config={config} members={members} onRefresh={refreshMembers} onSignOut={signOut}/>}
    </main>
    <nav className="mobile-bottom-nav" aria-label="Hauptnavigation">{pages.map(p => {
      const Icon = p.icon;
      return <button key={p.id} className={'bottom-link' + (page === p.id ? ' active' : '')} onClick={() => setPage(p.id)} aria-current={page === p.id ? 'page' : undefined}>
        <Icon size={22} stroke={page === p.id ? 2.5 : 1.7}/><span>{p.title}</span>
      </button>;
    })}</nav>
  </div>;
}

createRoot(document.getElementById('root')).render(<MantineProvider theme={theme} defaultColorScheme="dark"><App/></MantineProvider>);
