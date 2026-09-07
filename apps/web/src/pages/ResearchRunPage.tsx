import { ResearchRuntimeWorkspace, type ProjectionLifecycle } from "../components/ResearchRuntimeWorkspace";
import type { Phase4FrontendDataSource } from "../data/FrontendDataSource";
import type { ConnectionState, RunProjection } from "../types/domain";

export interface ResearchRunPageProps {
  readonly projection: RunProjection;
  readonly source: Phase4FrontendDataSource;
  readonly connection: ConnectionState;
  readonly lifecycle: ProjectionLifecycle | null;
  readonly onOpenResults: () => void;
  readonly onNavigate: (path: string) => void;
}

export function ResearchRunPage({ projection, source, connection, lifecycle, onOpenResults, onNavigate }: ResearchRunPageProps) {
  return <section className="research-run-page" aria-label={`${projection.object.companyName} Research Run`}>
    <ResearchRuntimeWorkspace projection={projection} source={source} connection={connection} lifecycle={lifecycle} onOpenResults={onOpenResults} onNavigate={onNavigate} />
  </section>;
}
