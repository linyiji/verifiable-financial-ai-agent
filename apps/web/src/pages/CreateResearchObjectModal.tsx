import { useRef, useState, type FormEvent } from "react";
import { OverlaySurface } from "../components/overlays/OverlaySurface";
import { createPhase4Mutation, type Phase4CreateResearchObjectInput, type Phase4Mutation } from "../data/FrontendDataSource";
import type { Phase4ResearchObjectDetail } from "../types/domain";
import { normalizeObjectInput, objectCreationFailure } from "./createObjectModel";

export function CreateResearchObjectModal({ onCreate, onCreated, onClose }: {
  readonly onCreate: (mutation: Phase4Mutation<Phase4CreateResearchObjectInput>) => Promise<Phase4ResearchObjectDetail>;
  readonly onCreated: (detail: Phase4ResearchObjectDetail) => void;
  readonly onClose: () => void;
}) {
  const [fields, setFields] = useState<Phase4CreateResearchObjectInput>({ symbol: "", companyName: "", exchange: "", currency: "", sector: null });
  const [pending, setPending] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const retained = useRef<Phase4Mutation<Phase4CreateResearchObjectInput> | null>(null);
  const close = () => { if (!inFlight.current) onClose(); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (inFlight.current) return;
    let mutation;
    try {
      const input = normalizeObjectInput(fields);
      mutation = retained.current;
      if (mutation === null || JSON.stringify(mutation.input) !== JSON.stringify(input)) {
        mutation = createPhase4Mutation(input);
        retained.current = mutation;
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请检查公司身份字段。");
      return;
    }
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const detail = await onCreate(mutation);
      onCreated(detail);
    } catch (caught) {
      const failure = objectCreationFailure(caught);
      setError(failure.message);
      setUncertain(failure.uncertain);
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };
  return <OverlaySurface kind="modal" titleId="create-object-title" onClose={close}>
    <form onSubmit={(event) => void submit(event)} data-testid="create-object-form">
      <div className="modal-head"><strong id="create-object-title">创建研究对象</strong><button type="button" className="btn ghost" aria-label="关闭创建研究对象" disabled={pending} onClick={close}>✕</button></div>
      <div className="modal-body">
        <p className="small">手动填写公司身份；当前不提供公司搜索或自动身份核验。股票代码唯一，不同交易所的同一代码不能重复创建。</p>
        {([ ["companyName", "公司名称", 200], ["symbol", "股票代码 / Ticker", 32], ["exchange", "交易所", 40], ["currency", "计价货币（三位代码）", 3], ["sector", "行业（可选）", 120] ] as const).map(([key, label, maxLength]) => <label className="field-label" key={key}>{label}<input
          className="text-input" name={key} data-autofocus={key === "companyName" ? true : undefined}
          required={key !== "sector"} maxLength={maxLength} disabled={pending || uncertain}
          autoComplete="off" value={fields[key] ?? ""}
          onChange={(event) => setFields((prior) => ({ ...prior, [key]: event.target.value }))}
        /></label>)}
        <p className="small">仅保存 Research Object，不创建研究 Run，不生成报告或借用其他公司的研究结果。</p>
        {error && <div className="alert" role="alert" data-testid="create-object-error">{error}</div>}
      </div>
      <div className="modal-foot"><button type="button" className="btn" disabled={pending} onClick={close}>取消</button><button type="submit" className="btn primary" data-testid="create-object-submit" disabled={pending}>{pending ? "正在创建…" : uncertain ? "重试同一创建请求" : "创建研究对象"}</button></div>
    </form>
  </OverlaySurface>;
}
