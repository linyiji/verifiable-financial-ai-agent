import { ResearchRuntimeWorkspace, type ProjectionLifecycle } from "../components/ResearchRuntimeWorkspace";
import type { ConnectionState, RunProjection } from "../types/domain";

export interface ResearchRunPageProps {
  readonly projection: RunProjection;
  readonly connection: ConnectionState;
  readonly lifecycle: ProjectionLifecycle | null;
  readonly onOpenResults: () => void;
}

export function ResearchRunPage({ projection, connection, lifecycle, onOpenResults }: ResearchRunPageProps) {
  return <section className="research-run-page" aria-label={`${projection.object.companyName} Research Run`}>
    <ResearchRuntimeWorkspace projection={projection} connection={connection} lifecycle={lifecycle} onOpenResults={onOpenResults} />
  </section>;
}
