import { NavLink } from "react-router-dom";

const tabs = [
  ["/agents", "Agents"],
  ["/tools", "Tools"],
  ["/skills", "Skills"],
  ["/collections", "Collections"],
  ["/guardrails", "Guardrails"],
] as const;

export function SingleAgentWorkspaceHeader() {
  return (
    <section className="single-workspace-heading">
      <div>
        <h1>Single-agent workspace</h1>
        <p>Build and manage focused AI agents and their resources.</p>
      </div>
      <nav className="workspace-tabs" aria-label="Single-agent workspace">
        {tabs.map(([path, label]) => (
          <NavLink key={path} to={path} className={({ isActive }) => isActive ? "active" : ""}>
            {label}
          </NavLink>
        ))}
      </nav>
    </section>
  );
}
