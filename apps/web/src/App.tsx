import { useEffect, useMemo, useState } from "react";
import { Phase4Application } from "./Phase4Application";
import { AppShell, type PrimaryPage } from "./components/shell/AppShell";
import { parseResultsRoute } from "./routing/resultsRoute";
import "./styles/application.css";
import "./styles/workspace-pages.css";

const ROUTE_CHANGE_EVENT = "phase4-routechange";

function activePage(): PrimaryPage {
  if (window.location.pathname === "/runs" || /^\/runs\/[^/]+$/u.test(window.location.pathname) || parseResultsRoute(window.location.pathname)) {
    return "runs";
  }
  if (window.location.pathname === "/objects" || /^\/objects\/[^/]+$/u.test(window.location.pathname)) {
    return "objects";
  }
  return "new";
}

function routeContext(page: PrimaryPage): string {
  if (parseResultsRoute(window.location.pathname)) return "Research Results";
  if (page === "runs") return "Research Run";
  if (page === "objects") return "Research Object";
  return "新建研究";
}

export default function App() {
  const [routeRevision, setRouteRevision] = useState(0);

  useEffect(() => {
    const syncRoute = () => {
      setRouteRevision((revision) => revision + 1);
    };
    window.addEventListener("popstate", syncRoute);
    window.addEventListener(ROUTE_CHANGE_EVENT, syncRoute);
    return () => {
      window.removeEventListener("popstate", syncRoute);
      window.removeEventListener(ROUTE_CHANGE_EVENT, syncRoute);
    };
  }, []);

  const page = useMemo(() => activePage(), [routeRevision]);

  const navigate = (destination: PrimaryPage) => {
    const target = destination === "runs" ? "/runs" : destination === "objects" ? "/objects" : "/";
    const current = `${window.location.pathname}${window.location.search}`;
    if (current === target) return;
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return <AppShell
    active={page}
    context={routeContext(page)}
    onNavigate={navigate}
  >
    <Phase4Application />
  </AppShell>;
}
