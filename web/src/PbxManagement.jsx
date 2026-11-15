import React, { useEffect, useState } from 'react';
import {
  Alert, Badge, Box, Button, Card, Divider, Group, MultiSelect, SimpleGrid,
  Stack, Text, TextInput, Title
} from '@mantine/core';
import { IconPhoneCalling, IconPlus, IconTrash, IconUsers } from '@tabler/icons-react';
import { api } from './api';

/**
 * A single administration surface for PBX extensions.
 * All mutations are protected server side by admin-role and CSRF checks.
 */
export default function PbxManagement({ csrf, members }) {
  const [directory, setDirectory] = useState({ groups: [], conferences: [] });
  const [group, setGroup] = useState({ extension: '6001', name: '', members: [] });
  const [conference, setConference] = useState({ extension: '3001', name: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function refresh() {
    const data = await api('/api/telephony/directory');
    setDirectory(data);
  }
  useEffect(() => {
    refresh().catch(err => setError(err.message));
  }, []);

  async function mutate(method, path, body) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await api(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) }, csrf);
      await refresh();
      setMessage(result.telephony_reload === false
        ? 'Gespeichert. FreeSWITCH ist derzeit nicht erreichbar – Status mit dem Diagnose-Skript prüfen.'
        : 'Konfiguration gespeichert und zur Telefonanlage übertragen.');
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveGroup(event) {
    event.preventDefault();
    if (await mutate('POST', '/api/admin/call-groups', group)) {
      setGroup({ extension: '6001', name: '', members: [] });
    }
  }
  async function saveConference(event) {
    event.preventDefault();
    if (await mutate('POST', '/api/admin/conferences', conference)) {
      setConference({ extension: '3001', name: '' });
    }
  }

  const options = members.filter(m => m.enabled).map(m => ({
    value: m.extension, label: m.display_name + ' · ' + m.extension
  }));

  return <Card withBorder radius="xl" p="xl" className="surface-card">
    <Group justify="space-between" align="start" mb="lg">
      <Box>
        <Group gap="sm"><IconPhoneCalling size={23}/><Title order={3}>Telefonanlage</Title></Group>
        <Text c="dimmed" mt={5} size="sm">Gemeinsame Nebenstellen, Rufgruppen und Audiokonferenzen verwalten.</Text>
      </Box>
      <Badge variant="light" color="cyan">FreeSWITCH</Badge>
    </Group>
    {error && <Alert color="red" mb="md" onClose={() => setError('')} withCloseButton>{error}</Alert>}
    {message && <Alert color="blue" mb="md" onClose={() => setMessage('')} withCloseButton>{message}</Alert>}
    <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
      <Stack gap="md">
        <Group justify="space-between"><Title order={4}>Rufgruppen</Title><Badge variant="light">{directory.groups.length}</Badge></Group>
        <form onSubmit={saveGroup}><Stack gap="sm">
          <TextInput label="Gruppenname" placeholder="Familie zuhause" required maxLength={80}
            value={group.name} onChange={e => setGroup(x => ({ ...x, name: e.currentTarget.value }))}/>
          <TextInput label="Nebenstelle · 6xxx" required pattern="6[0-9]{3}" placeholder="6001"
            value={group.extension} onChange={e => setGroup(x => ({ ...x, extension: e.currentTarget.value }))}/>
          <MultiSelect label="Mitglieder" placeholder="Teilnehmende auswählen" searchable clearable required
            data={options} maxValues={20} value={group.members}
            onChange={value => setGroup(x => ({ ...x, members: value }))}/>
          <Button type="submit" leftSection={<IconPlus size={16}/>} loading={busy}>Rufgruppe speichern</Button>
        </Stack></form>
        <Divider/>
        {directory.groups.length === 0 && <Text c="dimmed" size="sm">Noch keine Rufgruppen eingerichtet.</Text>}
        <Stack gap="xs">
          {directory.groups.map(g => <Group key={g.extension} justify="space-between" wrap="nowrap">
            <Box style={{ minWidth: 0 }}>
              <Text fw={700} truncate>{g.name} · {g.extension}</Text>
              <Text size="xs" c="dimmed">{g.members.join(', ')}</Text>
            </Box>
            <Button color="red" size="xs" variant="subtle" disabled={busy} aria-label={'Rufgruppe ' + g.extension + ' löschen'}
              leftSection={<IconTrash size={14}/>}
              onClick={() => mutate('DELETE', '/api/admin/call-groups/' + g.extension)}>Löschen</Button>
          </Group>)}
        </Stack>
      </Stack>
      <Stack gap="md">
        <Group justify="space-between"><Title order={4}>Audiokonferenzen</Title><Badge variant="light">{directory.conferences.length}</Badge></Group>
        <form onSubmit={saveConference}><Stack gap="sm">
          <TextInput label="Konferenzname" required placeholder="Familienrunde" maxLength={80}
            value={conference.name} onChange={e => setConference(x => ({ ...x, name: e.currentTarget.value }))}/>
          <TextInput label="Nebenstelle · 3xxx" required pattern="3[0-9]{3}"
            value={conference.extension} onChange={e => setConference(x => ({ ...x, extension: e.currentTarget.value }))}/>
          <Text size="xs" c="dimmed">Alle berechtigten Mitglieder können sich durch Wahl dieser Nummer zur selben Konferenz verbinden.</Text>
          <Button type="submit" loading={busy} leftSection={<IconPlus size={16}/>} variant="light">Konferenz speichern</Button>
        </Stack></form>
        <Divider/>
        <Stack gap="xs">
          {directory.conferences.map(c => <Group key={c.extension} justify="space-between" wrap="nowrap">
            <Box style={{ minWidth: 0 }}>
              <Text fw={700} truncate>{c.name} · {c.extension}</Text>
              <Text size="xs" c="dimmed">Audio-Konferenz</Text>
            </Box>
            <Button color="red" size="xs" variant="subtle" disabled={busy} leftSection={<IconTrash size={14}/>}
              aria-label={'Konferenz ' + c.extension + ' löschen'}
              onClick={() => mutate('DELETE', '/api/admin/conferences/' + c.extension)}>Löschen</Button>
          </Group>)}
        </Stack>
      </Stack>
    </SimpleGrid>
    <Alert variant="light" color="gray" mt="lg" title="Sicherheit">
      Interne Anrufe sind von kostenpflichtiger Providertelefonie getrennt. Ohne individuell aktivierte Berechtigung und explizite Providerfreigabe sind keine externen Gespräche möglich. Notrufnummern werden von FamiCom nicht unterstützt.
    </Alert>
  </Card>;
