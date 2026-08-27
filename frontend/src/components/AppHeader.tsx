import { Link, useLocation } from "react-router-dom";

import { useAuth } from "../AuthContext";

const titles: Record<string, string> = {
  "/agents": "Single-agent", "/tools": "Single-agent", "/skills": "Single-agent",
  "/collections": "Single-agent", "/guardrails": "Single-agent",
  "/multi-agent": "Multi-agent", "/workflows": "Workflows", "/chat": "Chat",
  "/providers": "AI providers",
  "/profile": "Profile",
};

export function AppHeader() {
  const { me } = useAuth();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const initials = me?.user.full_name?.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase() || "U";

  return (
    <header className="box topbar app-header dashboard-toolbar">
      {isHome ? <Link className="header-brand" to="/"><span className="brand">Mini Agent</span><span className="workspace">{me?.tenant_name} · {me?.user.full_name}</span></Link> : <div className="toolbar-breadcrumb"><Link to="/" aria-label="Go to home"><span aria-hidden="true">←</span> Home</Link><i /><strong>{titles[location.pathname] ?? "Workspace"}</strong></div>}
      <nav className="toolbar-actions" aria-label="Account controls">
        <button type="button" className="toolbar-icon" title="Notifications will be added in a later update" aria-label="Notifications"><svg viewBox="0 0 24 24"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg></button>
        <button type="button" className="toolbar-icon" title="Settings coming soon" aria-label="Settings"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.5 1a8 8 0 0 0-1.7-1L14.3 3h-4.6l-.4 3a8 8 0 0 0-1.7 1L5 6 3 9.4 5.1 11a7 7 0 0 0 0 2L3 14.6 5 18l2.6-1a8 8 0 0 0 1.7 1l.4 3h4.6l.4-3a8 8 0 0 0 1.7-1l2.6 1 2-3.4-2.1-1.6a7 7 0 0 0 .1-1Z"/></svg></button>
        <Link to="/profile" className="toolbar-avatar" title="Profile" aria-label="Profile">{initials}</Link>
      </nav>
    </header>
  );
}
