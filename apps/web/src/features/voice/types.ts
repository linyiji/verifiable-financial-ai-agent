/** Mirrors contracts/api/voice_session.py; media is a separately supplied port. */
export type VoiceLanguage = "auto" | "yue-HK";
export type VoiceStatus = 'connecting' | 'listening' | 'thinking' | 'waiting_run' | 'speaking' | 'reconnecting' | 'ended' | 'error';
export interface VoiceSession {
  language?: VoiceLanguage;
  interaction_mode?: 'preview' | 'conversation';
  id: string; user_id: string; room: string; status: VoiceStatus;
  started_at: string; expires_at: string; warning_at: string; remaining_seconds: number;
  task_id: string | null; chat_session_id: string | null; event_cursor: number; ended_reason: string | null;
}
export interface VoiceEvent {
  event_id: string; voice_session_id: string; cursor: number; status_seq: number;
  task_id: string | null; run_id?: string | null; occurred_at: string;
  kind: string; reason?: string | null; text?: string | null;
  source_event_id?: string | null; source_version?: string | null; data: Record<string, unknown>;
}
export interface VoiceCredentials { session: VoiceSession; url: string; token: string; token_expires_at: string; participant_identity: string }
export interface VoiceProviderAvailability {
  provider: 'quickrouter' | 'mimo' | 'unknown'; state: 'available' | 'unavailable' | 'unknown';
  blocked: boolean; reason: string; message: string; checked_at: string | null;
}
export interface VoiceAdapter {
  availability?(): Promise<VoiceProviderAvailability>;
  create(key: string, language?: VoiceLanguage): Promise<VoiceSession>;
  restore(id: string): Promise<VoiceSession>;
  bind(id: string, taskId: string, chatId?: string): Promise<VoiceSession>;
  credentials(id: string): Promise<VoiceCredentials>;
  events(id: string, after: number): Promise<{ session: VoiceSession; events: VoiceEvent[]; next_cursor: number; has_more: boolean }>;
  end(id: string): Promise<VoiceSession>;
}
/** No browser TTS or fabricated playback: room audio and barge-in belong to media transport. */
export interface VoiceMedia {
  connect(credentials: VoiceCredentials, onDisconnect: () => void): Promise<void>;
  mute(value: boolean): Promise<void>;
  disconnect(): void;
}
export interface VoiceSnapshot {
  availability?: VoiceProviderAvailability;
  language?: VoiceLanguage;
  session: VoiceSession | null; state: VoiceStatus | 'idle' | 'blocked'; busy: boolean;
  muted: boolean; structured: boolean; error: string | null;
  transcript: string; announcement: { text: string; reason: string } | null;
  remaining: number; warning: boolean; connected: boolean;
}
