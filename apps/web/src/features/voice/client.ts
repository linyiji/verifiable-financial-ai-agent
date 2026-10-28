import { VoiceHttpError } from './adapter';
import type { VoiceAdapter, VoiceMedia, VoiceSnapshot, VoiceSession, VoiceLanguage } from './types';
const initial: VoiceSnapshot = { language: "auto", session: null, state: 'idle', busy: false, muted: false, structured: true,
  error: null, transcript: '', announcement: null, remaining: 0, warning: false, connected: false };
export interface VoicePointer { read(): string | null; write(id: string | null): void }
export class VoiceClient {
  private value = initial;
  private listeners = new Set<() => void>();
  private generation = 0;
  private cursor = 0;
  private polling = false;
  private inputEpochs = new Map<string, number>();
  private key: string | null = null;
  private localEnded = false;
  private clockOffset = 0;
  private retryAt = 0;
  private retryDelay = 2000;
  constructor(private api: VoiceAdapter, private media: VoiceMedia, private pointer: VoicePointer,
    private now = () => Date.now()) {}
  getSnapshot = () => this.value;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private patch(next: Partial<VoiceSnapshot>) { this.value = { ...this.value, ...next }; this.listeners.forEach(fn => fn()); }
  private accept(session: VoiceSession) {
    if (!Number.isFinite(Date.parse(session.expires_at))) throw new Error('服务端语音到期时间无效');
    // remaining_seconds is server-derived, anchoring countdown despite client clock skew.
    this.clockOffset = Date.parse(session.expires_at) - session.remaining_seconds * 1000 - this.now();
    this.patch({ session, language: session.language ?? "auto", state: this.localEnded ? 'ended' : !this.value.connected && !['ended', 'error'].includes(session.status) ? 'connecting' : session.status });
    if (session.status === 'ended') {
      this.localEnded = true; this.retryAt = 0; this.key = null;
      this.media.disconnect(); this.patch({ connected: false, warning: false }); this.pointer.write(null);
      return;
    }
    this.tick();
  }
  private expireLocally() {
    if (this.localEnded) return;
    this.localEnded = true; this.retryAt = 0; this.key = null;
    this.media.disconnect(); this.pointer.write(null);
    this.patch({ state: 'ended', connected: false, warning: false,
      session: this.value.session ? { ...this.value.session, status: 'ended', ended_reason: 'expired' } : null });
  }
  tick = () => {
    const s = this.value.session;
    if (!s) return;
    const remaining = Math.max(0, Math.ceil((Date.parse(s.expires_at) - this.now() - this.clockOffset) / 1000));
    const warningAt = Date.parse(s.warning_at);
    this.patch({ remaining, warning: Number.isFinite(warningAt) &&
      this.now() + this.clockOffset >= warningAt && remaining > 0 });
    // The server owns natural expiry. Do not turn its fixed deadline into a
    // user-ended control request or create a replacement VoiceSession.
    if (!remaining && !this.localEnded) this.expireLocally();
    else if (remaining && !this.localEnded && this.retryAt && this.now() >= this.retryAt && !this.value.busy) {
      this.retryAt = 0; void this.reconnect();
    }
  };
  setLanguage = (language: VoiceLanguage) => {
    if (!this.value.busy && ["idle", "ended"].includes(this.value.state)) { this.key = null; this.patch({ language }); }
  };
  setStructured = (structured: boolean) => this.patch({ structured });
  refreshAvailability = async () => {
    if (!this.api.availability) return;
    try { this.patch({ availability: await this.api.availability() }); }
    catch { this.patch({ availability: { provider: 'unknown', state: 'unknown', blocked: true,
      reason: 'STATUS_UNAVAILABLE', message: '语音供应商状态暂时无法确认。', checked_at: null } }); }
  };
  private async requireAvailability() {
    await this.refreshAvailability();
    if (this.value.availability?.blocked) throw new VoiceHttpError(this.value.availability.message, 503, 'VOICE_PROVIDER_UNAVAILABLE');
  }
  clearTranscript = () => this.patch({ transcript: '' });
  private terminal(error: unknown) {
    if (!(error instanceof VoiceHttpError) || error.status !== 410) return false;
    this.localEnded = true; this.retryAt = 0; this.key = null;
    this.media.disconnect(); this.pointer.write(null);
    this.patch({ state: 'ended', connected: false, error: null,
      session: this.value.session ? { ...this.value.session, status: 'ended', ended_reason: 'expired' } : null });
    return true;
  }
  private async guarded(work: (epoch: number) => Promise<void>) {
    if (this.value.busy) return;
    const epoch = this.generation;
    this.patch({ busy: true, error: null });
    try { await work(epoch); }
    catch (e) { if (epoch === this.generation && !this.terminal(e)) this.patch({ error: e instanceof Error ? e.message : '语音操作失败', state: this.localEnded ? 'ended' : 'error' }); }
    finally { if (epoch === this.generation) this.patch({ busy: false }); }
  }
  start = () => this.guarded(async epoch => {
    if (this.value.session && (this.value.state !== 'ended' || this.value.session.status !== 'ended')) return;
    if (this.api.availability) await this.requireAvailability();
    if (epoch !== this.generation) return;
    const existing = this.pointer.read();
    if (existing && !this.value.session) {
      const restored = await this.api.restore(existing);
      if (epoch !== this.generation) return;
      this.cursor = restored.event_cursor; this.accept(restored);
      await this.connect(epoch); return;
    }
    this.localEnded = false;
    this.patch({ state: 'connecting', transcript: '', announcement: null });
    this.key ??= crypto.randomUUID();
    const session = await this.api.create(this.key, this.value.language ?? "auto");
    if (epoch !== this.generation) { await this.api.end(session.id); return; }
    this.pointer.write(session.id); this.cursor = 0; this.accept(session);
    await this.connect(epoch);
  });
  restore = () => this.guarded(async epoch => {
    const id = this.pointer.read(); if (!id) return;
    this.patch({ state: 'reconnecting' });
    const session = await this.api.restore(id);
    if (epoch !== this.generation) return;
    this.localEnded = false; this.cursor = session.event_cursor; this.accept(session);
    // Refresh never requests a new session or replays old announcements.
    if (session.status !== 'ended' && this.value.remaining) await this.connect(epoch);
  });
  private async connect(epoch: number) {
    if (!this.value.session || this.localEnded) return;
    if (this.api.availability) await this.requireAvailability();
    if (epoch !== this.generation) return;
    const credentials = await this.api.credentials(this.value.session.id);
    if (epoch !== this.generation) return;
    this.accept(credentials.session);
    if (!this.value.remaining || this.localEnded || credentials.session.status === 'ended') return;
    await this.media.connect(credentials, () => {
      if (epoch !== this.generation || this.localEnded) return;
      this.retryAt = this.now() + this.retryDelay;
      this.patch({ connected: false, state: 'reconnecting', error: '连接已断开，正在恢复同一通话。' });
    });
    if (epoch !== this.generation || this.localEnded) { this.media.disconnect(); return; }
    await this.media.mute(this.value.muted);
    this.retryDelay = 2000; this.retryAt = 0;
    this.patch({ connected: true, state: credentials.session.status, error: null });
  }
  reconnect = () => this.guarded(async epoch => {
    const id = this.value.session?.id ?? this.pointer.read(); if (!id || this.localEnded) return;
    this.media.disconnect(); this.patch({ connected: false, state: 'reconnecting' });
    const session = await this.api.restore(id);
    if (epoch !== this.generation) return;
    this.accept(session);
    try { await this.connect(epoch); }
    catch (error) { this.retryDelay = Math.min(30000, this.retryDelay * 2); this.retryAt = this.now() + this.retryDelay; throw error; }
  });
  bind = (taskId: string, chatId?: string) => this.guarded(async epoch => {
    const session = this.value.session;
    if (!session || this.localEnded || session.status === 'ended') return;
    if (session.task_id && session.task_id !== taskId) throw new Error('此通话已绑定其他 Task，请结束后为当前研究新建通话。');
    const bound = await this.api.bind(session.id, taskId, chatId);
    if (epoch === this.generation) this.accept(bound);
  });
  poll = async () => {
    const session = this.value.session;
    if (!session || this.localEnded || session.status === 'ended' || this.polling || this.value.busy) return;
    this.polling = true; const epoch = this.generation;
    try {
      const result = await this.api.events(session.id, this.cursor);
      if (epoch !== this.generation || this.localEnded) return;
      for (const event of result.events) {
        if (event.voice_session_id !== session.id || event.cursor <= this.cursor) continue;
        this.cursor = event.cursor;
        if (event.kind === 'transcript' && event.text) this.patch({ transcript: [this.value.transcript, event.text].filter(Boolean).join('\n'), error: null });
        if (event.kind === 'interruption' && typeof event.data.connection_id === 'string' && typeof event.data.input_epoch === 'number') {
          this.inputEpochs.set(event.data.connection_id, event.data.input_epoch);
          this.patch({ announcement: null });
        }
        if (event.kind === 'assistant_response' && event.text && event.task_id === result.session.task_id
            && typeof event.data.connection_id === 'string' && typeof event.data.input_epoch === 'number'
            && event.data.input_epoch >= (this.inputEpochs.get(event.data.connection_id) ?? 0))
          this.patch({ announcement: { text: event.text, reason: '普通对话回应' } });
        if (event.kind === 'turn_result' && ['failed', 'rejected'].includes(String(event.data.phase)) && event.text)
          this.patch({ error: event.text });
        if (event.kind === 'adapter_error' && event.text) this.patch({ error: event.text });
        if (event.kind === 'status_notice' && event.text) this.patch({ error: event.text });
        if (event.kind === 'announcement' && event.text && event.reason && event.task_id === result.session.task_id)
          this.patch({ announcement: { text: event.text, reason: event.reason } });
      }
      this.cursor = Math.max(this.cursor, result.next_cursor);
      this.accept(result.session);
      if (!this.value.connected && result.session.status !== 'ended') this.patch({ state: 'reconnecting' });
    } catch (e) { if (epoch === this.generation && !this.terminal(e)) this.patch({ state: 'reconnecting', error: e instanceof Error ? e.message : '读取语音事件失败' }); }
    finally { this.polling = false; }
  };
  mute = () => this.guarded(async () => { const muted = !this.value.muted; await this.media.mute(muted); this.patch({ muted }); });
  end = async () => {
    const epoch = ++this.generation; this.localEnded = true; this.retryAt = 0; this.media.disconnect();
    this.patch({ state: 'ended', connected: false, busy: true });
    const id = this.value.session?.id; if (!id) { this.patch({ busy: false }); return; }
    try { const ended = await this.api.end(id); if (epoch !== this.generation) return; this.accept(ended); this.pointer.write(null); this.key = null; }
    catch { if (epoch !== this.generation) return; this.patch({ error: '本机音频已关闭；服务端结束回执未确认，请重试结束。' }); }
    finally { if (epoch === this.generation) this.patch({ busy: false }); }
  };
}
