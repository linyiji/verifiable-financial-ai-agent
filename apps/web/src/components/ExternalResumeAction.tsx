import {useEffect, useRef, useState} from "react";

type ResumeState = {
  schema_version: "external-failure-control/v1"; run_id: string; state: string;
  binding_revision: number; current_cycle_id: string | null; cycle_status?: string;
  legal_actions: {command: "ResumeExternalFailure"; expectations: Record<string, unknown>}[];
};

export function decodeResumeState(value: unknown, runId: string): ResumeState {
  const v = value as ResumeState;
  if (!v || v.schema_version !== "external-failure-control/v1" || v.run_id !== runId
      || typeof v.state !== "string" || !Number.isSafeInteger(v.binding_revision)
      || !Array.isArray(v.legal_actions) || v.legal_actions.length > 1
      || v.legal_actions.some(a => a.command !== "ResumeExternalFailure"
        || a.expectations?.run_id !== runId || a.expectations?.actor !== "LOCAL_SINGLE_USER")) {
    throw new Error("Invalid Resume state");
  }
  return v;
}

/** Read-only refresh remains active during resumable terminal pauses. Only a click posts. */
export function ExternalResumeAction({runId, backendOrigin, onChanged}: {runId: string; backendOrigin: string; onChanged?: () => void}) {
  const [state, setState] = useState<ResumeState | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const generation = useRef(0);
  const revision = useRef<number | null>(null);
  const notify = useRef(onChanged);
  notify.current = onChanged;
  const url = `${backendOrigin}/api/research-runs/${encodeURIComponent(runId)}/external-resume`;
  const headers = {"X-Phase4-Contract-Version": "phase4-core/v1"};
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const refresh = async () => {
      const epoch = ++generation.current;
      try {
        const response = await fetch(url, {headers, cache: "no-store", signal: controller.signal});
        if (!response.ok) throw new Error("Read failed");
        const next = decodeResumeState(await response.json(), runId);
        if (active && epoch === generation.current) {
          setState(next);
          if (revision.current !== null && revision.current !== next.binding_revision) notify.current?.();
          revision.current = next.binding_revision;
        }
      } catch { if (active && epoch === generation.current) setState(null); }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [url, runId]);
  const act = async () => {
    if (locked.current || !state?.legal_actions.length) return;
    locked.current = true; setBusy(true); ++generation.current;
    const key = crypto.randomUUID();
    try {
      const response = await fetch(url, {method: "POST",
        headers: {...headers, "Content-Type": "application/json", "Idempotency-Key": key},
        body: JSON.stringify({...state.legal_actions[0].expectations,
          authorize_resume: true, idempotency_key: key})});
      const result = await response.json();
      if (result.projection) setState(decodeResumeState(result.projection, runId));
      else setState(null);
      notify.current?.();
      setMessage(response.ok ? "恢复授权已持久保存。" : "当前状态已改变，恢复请求未获授权。");
    } catch {
      setState(null); setMessage("连接中断，正在重新读取持久状态；不会自动重复授权。");
    } finally { locked.current = false; setBusy(false); }
  };
  if (!state && !message) return null;
  if (state && !state.legal_actions.length && !state.current_cycle_id && !message) return null;
  return <section className="card pad" aria-label="恢复外部失败">
    <p>恢复状态：{state?.state ?? "正在重新连接"}</p>
    {state?.cycle_status === "EXHAUSTED" && <p>本轮 Risk 调用已耗尽，已重新暂停。</p>}
    {Boolean(state?.legal_actions.length) && <>
      <p>保留本次研究及已完成结果，仅授权新的 Risk 执行周期（最多两次模型调用）。</p>
      <button className="button primary" disabled={busy} onClick={() => void act()}>明确授权 Resume</button>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
