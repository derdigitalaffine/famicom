import { api } from './api.js';

export async function loadIceConfiguration() {
  const result = await api('/api/telephony/ice');
  if (!Array.isArray(result.iceServers)) throw new Error('Ungültige ICE-Server-Konfiguration');
  return result;
}

/** RTCConfiguration for SIP.js 0.21.2. Never use SIP.js' public default STUN. */
export function sipIceOptions(ice) {
  return {
    peerConnectionConfiguration: { iceServers: ice?.iceServers ?? [] },
    iceGatheringTimeout: 10000
  };
}

/** Relay-only ICE probe. Does not disclose candidates or user IP addresses. */
export async function probeTurnRelay(ice, RTC = globalThis.RTCPeerConnection, waitMs = 10000) {
  if (!ice?.enabled) return { available: false, reason: 'TURN ist deaktiviert.' };
  if (!RTC) return { available: false, reason: 'Dein Browser unterstützt WebRTC nicht.' };
  const pc = new RTC({ iceServers: ice.iceServers, iceTransportPolicy: 'relay' });
  let timer;
  try {
    const found = new Promise(resolve => {
      let done = false;
      const complete = result => {
        if (done) return;
        done = true;
        resolve(result);
      };
      pc.onicecandidate = event => {
        const candidate = event.candidate;
        if (candidate && (candidate.type === 'relay' || / typ relay(?: |$)/.test(candidate.candidate || ''))) {
          complete({ available: true, reason: 'TURN-Relay-Kandidat empfangen.' });
        } else if (!candidate) {
          complete({ available: false, reason: 'ICE abgeschlossen, kein Relay-Kandidat erreichbar.' });
        }
      };
      pc.onicegatheringstatechange = () => {
        if (pc.iceGatheringState === 'complete') {
          complete({ available: false, reason: 'Keine TURN-Relay-Adresse erhalten.' });
        }
      };
      timer = setTimeout(() => complete({ available: false, reason: 'TURN-Test hat das Zeitlimit erreicht.' }), waitMs);
    });
    pc.createDataChannel('turn-diagnostic');
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    return await found;
  } finally {
    clearTimeout(timer);
    pc.close();
  }
}
