import type { VoiceAdapter } from './types';

export class VoiceHttpError extends Error {
  constructor(message: string, public status: number, public code?: string) { super(message); }
}

/** Authentication is supplied by the host, never a bundled token or invented endpoint. */
export function createVoiceHttpAdapter(headers: () => Promise<Record<string, string>>): VoiceAdapter {
  async function request<T>(path: string, method = 'GET', body?: object, extra = {}): Promise<T> {
    const response = await fetch(`/api/voice-sessions${path}`, {
      method, credentials: 'same-origin', signal: AbortSignal.timeout(15000),
      headers: { 'Content-Type': 'application/json', ...await headers(), ...extra },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new VoiceHttpError(payload?.error?.message ?? payload?.detail?.message ?? `语音接口不可用（${response.status}）`, response.status, payload?.error?.code);
    }
    return response.json();
  }
  const path = (id: string) => `/${encodeURIComponent(id)}`;
  return {
    availability: () => request('/availability'),
    create: (key, language = 'auto') => request('', 'POST', { interaction_mode: 'conversation', language }, { 'Idempotency-Key': key }),
    restore: id => request(path(id)),
    bind: (id, taskId, chatId) => request(`${path(id)}/binding`, 'PUT', { task_id: taskId, chat_session_id: chatId ?? null }),
    credentials: id => request(`${path(id)}/credentials`, 'POST'),
    events: (id, after) => request(`${path(id)}/events?after=${after}`),
    end: id => request(`${path(id)}/end`, 'POST'),
  };
}
