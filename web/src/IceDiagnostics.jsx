import React, { useState } from 'react';
import { Alert, Badge, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconAntennaBars5, IconRefresh } from '@tabler/icons-react';
import { loadIceConfiguration, probeTurnRelay } from './ice';

/** Intentionally does not print SDP, ICE candidates, IPs or TURN credentials. */
export default function IceDiagnostics() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [enabled, setEnabled] = useState(null);
  async function test() {
    setBusy(true); setResult(null);
    try {
      const ice = await loadIceConfiguration();
      setEnabled(ice.enabled);
      setResult(await probeTurnRelay(ice));
    } catch (error) {
      setResult({ available: false, reason: error?.message || 'Diagnose fehlgeschlagen' });
    } finally {
      setBusy(false);
    }
  }
  return <Card withBorder radius="xl" p="xl" className="surface-card">
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={4}>WebRTC-Verbindung</Title>
        {enabled !== null && <Badge variant="light" color={enabled ? 'teal' : 'gray'}>{enabled ? 'TURN aktiviert' : 'Nur lokales ICE'}</Badge>}
      </Group>
      <Text c="dimmed" size="sm">Prüft, ob der Browser einen Relay-Kandidaten erhält. Es werden keine IP-Adressen oder Zugangsdaten angezeigt.</Text>
      <Button variant="light" loading={busy} leftSection={<IconRefresh size={16}/>} onClick={test}>
        TURN-Verbindung testen
      </Button>
      {result && <Alert color={result.available ? 'teal' : enabled ? 'yellow' : 'blue'} icon={<IconAntennaBars5 size={16}/>}>
        {result.reason}
        {result.available && ' Ein erfolgreicher Zwei-Geräte-Sprachtest ist trotzdem erforderlich.'}
      </Alert>}
    </Stack>
  </Card>;
}
