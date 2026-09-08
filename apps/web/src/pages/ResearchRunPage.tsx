import { ResearchRuntimeWorkspace, type ProjectionLifecycle } from "../components/ResearchRuntimeWorkspace";
import { ReexecutionAction } from "../components/ReexecutionAction";
import { RuntimeRecoveryEvidence } from "../components/results/RuntimeRecoveryEvidence";
import type { Phase4FrontendDataSource } from "../data/FrontendDataSource";
import type { RunStageRoute } from "../routing/resultsRoute";
import type { ConnectionState, RunProjection } from "../types/domain";

export interface ResearchRunPageProps {
  readonly projection: RunProjection;
  readonly source: Phase4FrontendDataSource;
  readonly connection: ConnectionState;
  readonly lifecycle: ProjectionLifecycle | null;
  readonly selectedStage: RunStageRoute;
  readonly onSelectStage: (stage: RunStageRoute) => void;
  readonly backendOrigin: string;
  readonly onOpenResults: () => void;
  readonly onOpenExecution: () => void;
  readonly onNavigate: (path: string) => void;
}

export function ResearchRunPage({ projection, source, connection, lifecycle, selectedStage, onSelectStage, backendOrigin, onOpenResults, onOpenExecution, onNavigate }: ResearchRunPageProps) {
  return <section className="research-run-page" aria-label={`${projection.object.companyName} Research Run`}>
    <ReexecutionAction key={projection.run.runId} runId={projection.run.runId} objectId={projection.object.objectId} failed={projection.run.status === "FAILED"} backendOrigin={backendOrigin} onNavigate={onNavigate} />
    <ResearchRuntimeWorkspace projection={projection} source={source} connection={connection} lifecycle={lifecycle} selectedStage={selectedStage} onSelectStage={onSelectStage} backendOrigin={backendOrigin} onOpenResults={onOpenResults} onOpenExecution={onOpenExecution} onNavigate={onNavigate} />
    {projection.terminal.isTerminal && <details><summary>模型执行与恢复记录（只读）</summary><RuntimeRecoveryEvidence source={source} runId={projection.run.runId} objectId={projection.object.objectId} /></details>}
  </section>;
}
