import type { ReactNode } from "react";

export type PrimaryPage = "new" | "runs" | "objects";

export interface AppShellProps {
  readonly active: PrimaryPage;
  readonly context: string;
  readonly onNavigate: (page: PrimaryPage) => void;
  readonly children: ReactNode;
}

const NAVIGATION: readonly {
  id: PrimaryPage;
  icon: string;
  label: string;
}[] = [
  { id: "new", icon: "＋", label: "新建研究" },
  { id: "runs", icon: "▤", label: "研究记录" },
  { id: "objects", icon: "◫", label: "Research Object" }
];

export function AppShell({ active, context, onNavigate, children }: AppShellProps) {
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-logo" src="/verifiable-financial-agent-logo.png" alt="" width="32" height="32" />
        <div>
          <div className="brand-title">向风行 AI</div>
          <div className="brand-sub">Verifiable Financial Agent</div>
        </div>
      </div>
      <div className="nav-label">Research</div>
      {NAVIGATION.map((item) => <button
        type="button"
        key={item.id}
        className={`nav-item ${active === item.id ? "active" : ""}`}
        aria-current={active === item.id ? "page" : undefined}
        onClick={() => onNavigate(item.id)}
      >
        <span className="nav-icon" aria-hidden="true">{item.icon}</span>
        {item.label}
      </button>)}
      <div className="sidebar-foot">
        <div className="health"><span className="health-dot" />真实运行数据</div>
        <div className="micro sidebar-caption">研究计划 → 执行 → 结果 → 验证</div>
      </div>
    </aside>

    <header className="topbar">
      <div className="top-context"><span>研究工作区</span><span>›</span><strong>{context}</strong></div>
      <div className="top-actions">
        <span className="chip"><span className="health-dot compact-dot" />实时投影</span>
        <div className="avatar" aria-label="向风行 AI">ZF</div>
      </div>
    </header>

    <nav className="mobile-nav" aria-label="主导航">
      {NAVIGATION.map((item) => <button
        type="button"
        key={item.id}
        className={active === item.id ? "active" : ""}
        onClick={() => onNavigate(item.id)}
      >
        <span aria-hidden="true">{item.icon}</span>{item.label}
      </button>)}
    </nav>

    <main className="app-main">{children}</main>
  </div>;
}
