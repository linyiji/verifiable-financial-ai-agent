import { useEffect, useRef, useState } from "react";

type Authorization = {
  authorization_id: string; research_object_id: string; reexecution_of_run_id: string;
  scheme_id: string; scheme_hash: string; base_run_id: string; base_research_view_version: string;
  expires_at: string;
};

/** Two explicit user actions. Never prepare, generate a Scheme, or retry a failed POST. */
export function ReexecutionAction({runId, objectId, failed, backendOrigin, onNavigate}: {
  runId: string; objectId: string; failed: boolean; backendOrigin: string;
  onNavigate: (path: string) => void;
}) {
  const [detail, setDetail] = useState<{base_run_id?: string; reexecution_of_run_id?: string} | null>(null);
  const [authorization, setAuthorization] = useState<Authorization | null>(null);
  const [stopped, setStopped] = useState(false);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const headers = {"X-Phase4-Contract-Version": "phase4-core/v1"};
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${backendOrigin}/api/research-runs/${encodeURIComponent(runId)}`, {headers, signal: controller.signal})
      .then(async response => response.ok ? response.json() : null).then(setDetail).catch(() => {});
    return () => controller.abort();
  }, [runId, backendOrigin]);
  const act = async () => {
    if (locked.current || stopped) return;
    if (authorization && Date.now() >= Date.parse(authorization.expires_at)) {setStopped(true); return;}
    locked.current = true; setBusy(true);
    try {
      const suffix = authorization ? "reexecute" : "reexecution-authorizations";
      const response = await fetch(`${backendOrigin}/api/research-runs/${encodeURIComponent(runId)}/${suffix}`, {
        method: "POST", headers: {...headers, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID()},
        body: JSON.stringify(authorization
          ? {research_object_id: objectId, authorization_id: authorization.authorization_id}
          : {research_object_id: objectId, authorize_reexecution: true}),
      });
      if (!response.ok) throw new Error("Stopped");
      const value = await response.json();
      if (value.research_object_id !== objectId || value.reexecution_of_run_id !== runId) throw new Error("Identity mismatch");
      if (authorization) {
        if (value.authorization_id !== authorization.authorization_id || value.scheme_id !== authorization.scheme_id
          || value.scheme_hash !== authorization.scheme_hash || value.base_run_id !== authorization.base_run_id
          || value.base_research_view_version !== authorization.base_research_view_version
          || typeof value.run_id !== "string" || !value.run_id.startsWith("RUN-") || value.run_id === runId) throw new Error("Identity mismatch");
        onNavigate(`/runs/${encodeURIComponent(value.run_id)}`);
      } else {
        if ([value.authorization_id, value.scheme_id, value.base_run_id, value.base_research_view_version].some(x => typeof x !== "string" || !x.trim())
          || !/^sha256:[a-f0-9]{64}$/.test(value.scheme_hash) || !Number.isFinite(Date.parse(value.expires_at))) throw new Error("Invalid authorization");
        setAuthorization(value); locked.current = false;
      }
    } catch { setStopped(true); }
    finally { setBusy(false); }
  };
  if (!detail?.base_run_id) return null;
  return <section className="card pad" aria-label="重新执行研究">
    {detail.reexecution_of_run_id && <p>这是沿用同一研究方案的新执行记录。<a href={`/runs/${encodeURIComponent(detail.reexecution_of_run_id)}`}>查看上次失败执行</a></p>}
    {failed && <>
      <p>本次执行失败。重新执行将沿用同一研究方案和知识基线，创建新的执行记录；历史失败记录不会修改。</p>
      {authorization && <p>授权已保存。确认后将生成新的执行任务图，不重新生成研究方案。授权截止：{new Date(authorization.expires_at).toLocaleString()}</p>}
      <button className="button primary" disabled={busy || stopped || Boolean(authorization && Date.now() >= Date.parse(authorization.expires_at))} onClick={() => void act()}>
        {busy ? "正在处理…" : authorization ? "确认沿用方案并重新执行" : "重新执行"}
      </button>
      {stopped && <p role="alert">操作已停止。请检查服务端结果，不要重复提交。</p>}
    </>}
  </section>;
}
