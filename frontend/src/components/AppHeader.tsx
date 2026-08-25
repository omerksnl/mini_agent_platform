import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../AuthContext";

const singleAgentRoutes = ["/", "/tools", "/skills", "/collections"];

export function AppHeader() {
  const { me, logout } = useAuth();
  const location = useLocation();
  const singleActive = singleAgentRoutes.includes(location.pathname);
  const active = (path: string) => location.pathname === path ? "active" : "";

  return (
    <header className="box topbar app-header">
      <Link className="header-brand" to="/">
        <span className="brand">Mini Agent</span>
        <span className="workspace">{me?.tenant_name} · {me?.user.full_name}</span>
      </Link>
      <nav className="topbar-actions" aria-label="Main navigation">
        <div className={`nav-menu ${singleActive ? "active" : ""}`}>
          <button type="button" className="nav-menu-trigger">Single-agent <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.7 9.3a1 1 0 0 1 1.4 0l3.9 3.9 3.9-3.9a1 1 0 1 1 1.4 1.4l-4.6 4.6a1 1 0 0 1-1.4 0l-4.6-4.6a1 1 0 0 1 0-1.4Z" /></svg></button>
          <div className="nav-menu-popover">
            <Link className={active("/")} to="/"><strong>Agents</strong><small>Create and configure agents</small></Link>
            <Link className={active("/tools")} to="/tools"><strong>Tools</strong><small>Connect callable capabilities</small></Link>
            <Link className={active("/skills")} to="/skills"><strong>Skills</strong><small>Reusable agent instructions</small></Link>
            <Link className={active("/collections")} to="/collections"><strong>Collections</strong><small>Searchable knowledge sources</small></Link>
          </div>
        </div>
        <Link className={`nav-link ${active("/multi-agent")}`} to="/multi-agent">Multi-agent</Link>
        <Link className={`nav-link ${active("/workflows")}`} to="/workflows">Workflows</Link>
        <Link className={`nav-link ${active("/chat")}`} to="/chat">Chat</Link>
        <Link className={`nav-link ${active("/settings/provider")}`} to="/settings/provider">AI provider</Link>
        <button type="button" className="nav-link nav-signout" onClick={logout}>Sign out</button>
      </nav>
    </header>
  );
}
