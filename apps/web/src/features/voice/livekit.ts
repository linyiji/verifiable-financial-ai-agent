import { Room, RoomEvent, Track, createLocalAudioTrack, type LocalAudioTrack } from 'livekit-client';
import type { VoiceCredentials, VoiceMedia } from './types';

/** All rejoin attempts go through VoiceClient and fresh, authorized credentials.
 * SDK autonomous retries are disabled so a server 410 is final. Tokens stay on the
 * stack/SDK instance; disconnect releases that instance and every captured track.
 */
function diagnostic(event: string, detail: Record<string, unknown> = {}) {
  // Local development observability: no credentials, SDP, transcript, or device IDs.
  if (['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))
    window.dispatchEvent(new CustomEvent('vefin-voice-media', { detail: { event, at: Date.now(), ...detail } }));
}
export class LiveKitVoiceMedia implements VoiceMedia {
  private room?: Room;
  private mic?: LocalAudioTrack;
  private deadline?: ReturnType<typeof setTimeout>;
  private transportWatchdog?: ReturnType<typeof setInterval>;
  private generation = 0;
  private elements = new Set<HTMLMediaElement>();
  private playbackButton?: HTMLButtonElement;

  async connect(credentials: VoiceCredentials, onDisconnect: () => void) {
    this.disconnect();
    const epoch = this.generation;
    const persistedDuration = Date.parse(credentials.session.expires_at) - Date.parse(credentials.session.started_at);
    const remaining = Math.min(persistedDuration, credentials.session.remaining_seconds * 1000);
    if (remaining <= 0) throw new Error('通话已到期，请重新开始。');
    const room = new Room({ reconnectPolicy: { nextRetryDelayInMs: () => null },
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    this.room = room;
    this.deadline = setTimeout(() => { this.disconnect(); onDisconnect(); }, remaining);
    const current = () => epoch === this.generation && this.room === room;
    room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
      if (!current() || track.kind !== Track.Kind.Audio || !participant.identity.startsWith('agent:')) return;
      diagnostic('worker_track_subscribed', { readyState: track.mediaStreamTrack.readyState, trackSid: _publication.trackSid, mediaTrackId: track.mediaStreamTrack.id });
      const element = track.attach();
      element.setAttribute('data-vefin-worker-audio', 'true');
      element.setAttribute('data-vefin-track-sid', _publication.trackSid);
      element.setAttribute('data-vefin-media-connection', String(epoch));
      element.hidden = true;
      this.elements.add(element); document.body.appendChild(element);
    });
    room.on(RoomEvent.TrackUnsubscribed, track => {
      for (const element of track.detach()) { this.elements.delete(element); element.remove(); }
    });
    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      if (!current()) return;
      if (room.canPlaybackAudio) { this.playbackButton?.remove(); this.playbackButton = undefined; }
      else if (!this.playbackButton) {
        const button = document.createElement('button');
        button.textContent = '点击开启 VeFin 语音播放';
        button.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:10000;padding:12px';
        button.onclick = () => { void room.startAudio().catch(() => { button.textContent = '播放未开启，请再次点击'; }); };
        document.body.appendChild(button); this.playbackButton = button;
      }
    });
    room.on(RoomEvent.Disconnected, reason => {
      diagnostic('room_disconnected', { reason });
      if (current()) { this.disconnect(); onDisconnect(); }
    });
    try {
      // Request a real microphone. A canceled permission prompt must not leak a late track.
      let permissionTimer: ReturnType<typeof setTimeout> | undefined;
      diagnostic('microphone_requested');
      const capture = createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true });
      void capture.then(track => { if (!current()) track.stop(); }, () => {});
      let mic: LocalAudioTrack;
      try {
        mic = await Promise.race([capture, new Promise<never>((_, reject) => {
          permissionTimer = setTimeout(() => reject(new Error('等待麦克风授权超时。请允许当前网站的麦克风权限，再点击恢复连接。')), 25000);
        })]);
      } finally { clearTimeout(permissionTimer); }
      if (!current()) { mic.stop(); return; }
      this.mic = mic;
      diagnostic('microphone_acquired', { readyState: mic.mediaStreamTrack.readyState, enabled: mic.mediaStreamTrack.enabled });
      await room.connect(credentials.url, credentials.token, { maxRetries: 0 });
      if (!current()) return;
      diagnostic('room_connected', { state: room.state });
      const publication = await room.localParticipant.publishTrack(mic, { source: Track.Source.Microphone });
      diagnostic('microphone_published', { trackSid: publication.trackSid, readyState: mic.mediaStreamTrack.readyState });
      if (!current()) return;
      // The pinned SDK waits three reconciliation intervals when a transport
      // closes without a signalling failure. Probe only after publication;
      // CONNECTING remains healthy during normal renegotiation. Credential
      // refresh, backoff and the fixed deadline still belong to VoiceClient.
      let failures = 0;
      let transportEstablished = false;
      const establishedTransports = new Set<object>();
      this.transportWatchdog = setInterval(() => {
        if (!current()) return;
        const probe = room.engine?.verifyTransport;
        if (typeof probe !== 'function') return; // SDK compatibility fallback.
        const manager = room.engine.pcManager;
        const transports = [manager?.publisher, manager?.subscriber].filter(Boolean);
        let terminated = false;
        for (const transport of transports) {
          const state = transport?.getConnectionState();
          if (state === 'connected') establishedTransports.add(transport!);
          if (transport && establishedTransports.has(transport)
              && (state === 'closed' || state === 'failed')) terminated = true;
        }
        // Aggregate SDK state can remain CONNECTING after a native PC closes.
        // Only previously connected transports can cause fast recovery.
        if (!terminated && probe.call(room.engine)) { transportEstablished = true; failures = 0; return; }
        // A subscriber may still be waiting for the Worker to join. Do not
        // mistake initial setup for a previously established transport failure.
        if (!transportEstablished) return;
        if (++failures < 2) return;
        diagnostic('transport_unhealthy');
        this.disconnect(); onDisconnect();
      }, 1000);
      void room.startAudio().catch(() => { /* playback button follows SDK status */ });
    } catch (error) {
      diagnostic('media_error', { name: error instanceof Error ? error.name : 'unknown' });
      if (current()) this.disconnect();
      if (error instanceof Error && error.name === 'NotAllowedError')
        throw new Error('麦克风权限未开启。请在浏览器允许麦克风后点击恢复连接；文字草稿已保留。');
      if (error instanceof Error && error.name === 'NotFoundError') throw new Error('没有可用麦克风，请连接设备后恢复通话。');
      throw error;
    }
  }
  async mute(value: boolean) {
    if (!this.mic) throw new Error('麦克风未连接');
    if (value) await this.mic.mute(); else await this.mic.unmute();
    diagnostic('microphone_muted', { muted: value, readyState: this.mic.mediaStreamTrack.readyState });
  }
  disconnect() {
    this.generation++;
    clearTimeout(this.deadline); this.deadline = undefined;
    clearInterval(this.transportWatchdog); this.transportWatchdog = undefined;
    const room = this.room; this.room = undefined;
    this.mic?.stop();
    if (this.mic) diagnostic('microphone_stopped', { readyState: this.mic.mediaStreamTrack.readyState });
    this.mic = undefined;
    for (const element of this.elements) { element.pause(); element.srcObject = null; element.remove(); }
    this.elements.clear(); this.playbackButton?.remove(); this.playbackButton = undefined;
    if (room) { room.removeAllListeners(); void room.disconnect(true); }
  }
}
