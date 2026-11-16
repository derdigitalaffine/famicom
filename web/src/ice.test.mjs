import test from 'node:test';
import assert from 'node:assert/strict';
import { sipIceOptions, probeTurnRelay } from './ice.js';

test('never uses a third-party default STUN server', () => {
  assert.deepEqual(sipIceOptions({ enabled: false, iceServers: [] }).peerConnectionConfiguration, { iceServers: [] });
});

test('passes coturn ICE servers to SIP.js unchanged', () => {
  const ice = [{urls:'turn:example.org:3478?transport=udp',username:'1234:a',credential:'secret'}];
  assert.deepEqual(sipIceOptions({iceServers:ice}).peerConnectionConfiguration.iceServers, ice);
});

test('relay-only diagnostic confirms a relayed ICE candidate without printing its IP', async () => {
  class Peer {
    constructor(config) { this.config = config; assert.equal(config.iceTransportPolicy, 'relay'); }
    createDataChannel() { return {}; }
    async createOffer() { return {type:'offer',sdp:'private-sdp'}; }
    async setLocalDescription() {
      this.onicecandidate?.({candidate:{candidate:'candidate:1 1 udp 1 192.0.2.1 5000 typ relay',type:'relay'}});
    }
    close() { this.closed = true; }
  }
  const r = await probeTurnRelay({enabled:true,iceServers:[{urls:'turn:example.org:3478'}]}, Peer, 500);
  assert.equal(r.available, true);
  assert.equal(JSON.stringify(r).includes('192.0.2.1'), false);
});
test('disabled TURN does not create a connection', async () => {
  const r = await probeTurnRelay({enabled:false,iceServers:[]});
  assert.equal(r.available,false);
});
