import { useEffect, useState } from "react";
import { HttpFrontendDataSource } from "../data/HttpFrontendDataSource";
import { createPhase4Mutation } from "../data/FrontendDataSource";
import { Phase4ApiClient } from "../api/client";
import { IncrementalContext } from "../components/IncrementalContext";
import { decodePreparedResearchDraft, type PreparedResearchDraft } from "../types/domain";

type Review = {draft: PreparedResearchDraft; expires: string; valid: boolean; consumed: boolean; renewed: boolean};

export function ExactDraftReviewPage({draftId, backendOrigin}: {draftId: string; backendOrigin: string}) {
  const [review, setReview] = useState<Review | null>(null);
  const [failed, setFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmationFailed, setConfirmationFailed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setReview(null); setFailed(false);
    const client = new Phase4ApiClient({baseUrl: backendOrigin});
    void client.requestJson({method: "GET", path: `/api/research-drafts/${encodeURIComponent(draftId)}`,
      expectedStatuses: [200], signal: controller.signal,
      decode: (value: unknown): Review => {
        if (!value || typeof value !== "object") throw new Error("Invalid exact draft review");
        const v = value as Record<string, unknown>;
        const draft = decodePreparedResearchDraft(v.draft);
        if (draft.draftId !== draftId || typeof v.effective_expires_at !== "string" ||
          !Number.isFinite(Date.parse(v.effective_expires_at)) || typeof v.lease_valid !== "boolean" ||
          typeof v.consumed !== "boolean" || !(v.lease_id === null || typeof v.lease_id === "string")) throw new Error("Invalid lease identity");
        return {draft, expires: v.effective_expires_at, valid: v.lease_valid, consumed: v.consumed, renewed: v.lease_id !== null};
      }}).then(setReview).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [draftId, backendOrigin]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer);}, []);
  if (failed) return <div className="card pad" role="alert">无法安全载入该研究方案。不会生成替代方案。</div>;
  if (!review) return <div className="card pad" role="status">正在读取已保存的研究方案…</div>;
  const d = review.draft, context = d.schemeSnapshot.incrementalContext;
  const valid = review.valid && !review.consumed && now < Date.parse(review.expires);
  const confirmExact = async () => {
    if (!valid || attempted) return;
    setAttempted(true); setConfirming(true);
    try {
      const source = new HttpFrontendDataSource({baseUrl: backendOrigin});
      const result = await source.confirmResearchRun(createPhase4Mutation({
        draftId: d.draftId, draftVersion: d.draftVersion, draftHash: d.draftHash,
        researchObjectId: d.objectId, confirmScheme: true,
        expectedGoalId: d.goal.goalId, expectedSchemeId: d.schemeSnapshot.schemeId,
      }));
      window.location.assign(`/runs/${encodeURIComponent(result.admission.runId)}`);
    } catch {
      setConfirmationFailed(true); setConfirming(false);
    }
  };
  return <main className="app-content" data-testid="exact-draft-review" data-draft-id={d.draftId} data-draft-hash={d.draftHash}>
    <section className="card pad">
      <h1>重新确认该研究方案</h1>
      <p>{review.renewed ? "确认授权已续期；" : "已保存的研究方案；"}方案内容保持不变，没有重新生成 AI 研究方案。</p>
      <p><a href={`/objects/${encodeURIComponent(d.objectId)}`}>Research Object · {d.objectId}</a></p>
      <p>{d.goal.goalText}</p>
      <p data-testid="draft-lease-status">{review.consumed ? "该方案已确认" : valid ? "确认授权有效" : "确认授权已过期"} · 截止 {new Date(review.expires).toLocaleString()}</p>
      <p>读取与复核不调用模型。确认后仅将此已保存方案分解为执行任务图，不重新生成研究方案；任务图验证通过后才创建独立 Research Run。</p>
      <button className="button primary" disabled={!valid || attempted} onClick={() => void confirmExact()}>{confirming ? "正在验证任务图…" : "确认此方案并开始研究"}</button>
      {confirmationFailed && <p role="alert">确认未完成，已停止。请检查服务端结果；不要重复确认或重新生成方案。</p>}
      <h2>研究范围</h2><ul>{d.schemeSnapshot.researchScope.map((item, i) => <li key={i}>{item}</li>)}</ul>
      <h2>数据与报告要求</h2><ul>{[...d.schemeSnapshot.dataRequirements, ...d.schemeSnapshot.reportRequirements].map((item, i) => <li key={i}>{item}</li>)}</ul>
    </section>
    {context && <>
      <section className="card pad"><h2>本次增量决策</h2><p>{["REUSE", "REFRESH", "REVALIDATE", "PREVENT", "UNKNOWN"].map(k => `${k} = ${context.decisions.filter(x => x.decision === k).length}`).join(" · ")}</p>
        <p>历史记忆仅用于规划，不代表沿用历史批准或新获取的证据。</p>
        <a href={`/runs/${encodeURIComponent(context.base_run_id)}/results/report`}>查看确切历史研究 · {context.base_run_id}</a><p>Base View · {context.base_research_view_version}</p>
      </section><IncrementalContext context={context}/>
    </>}
    <details className="card pad"><summary>方案身份与校验</summary><dl>
      <dt>Draft ID</dt><dd>{d.draftId}</dd><dt>Scheme ID</dt><dd>{d.schemeSnapshot.schemeId}</dd>
      <dt>Draft Hash</dt><dd>{d.draftHash}</dd><dt>Draft Version</dt><dd>{d.draftVersion}</dd>
    </dl></details>
  </main>;
}
