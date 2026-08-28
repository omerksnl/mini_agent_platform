import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { api, type Agent } from "../api";
import { AppHeader } from "../components/AppHeader";
import { useAuth } from "../AuthContext";

const cards = [
  { to: "/agents", title: "Single-agent", description: "Create and manage focused AI agents", icon: "agent" },
  { to: "/multi-agent", title: "Multi-agent", description: "Coordinate teams of specialized agents", icon: "team" },
  { to: "/workflows", title: "Workflows", description: "Automate repeatable tasks and processes", icon: "flow" },
  { to: "/chat", title: "Chat", description: "Start a conversation with your agents", icon: "chat" },
  { to: "/providers", title: "AI providers", description: "Manage models, credentials and routing", icon: "cloud" },
  { to: "/visual-models", title: "Visual models", description: "Configure image recognition models", icon: "vision" },
] as const;

function CardIcon({ name }: { name: string }) {
  if (name === "team") return <svg viewBox="0 0 48 48"><circle cx="16" cy="16" r="7"/><circle cx="33" cy="17" r="6"/><path d="M4 39c1-9 6-14 13-14s12 5 13 14M27 29c2-3 5-5 8-5 6 0 10 5 10 13"/></svg>;
  if (name === "flow") return <svg viewBox="0 0 48 48"><rect x="17" y="4" width="14" height="10" rx="2"/><rect x="3" y="34" width="14" height="10" rx="2"/><rect x="31" y="34" width="14" height="10" rx="2"/><path d="M24 14v10M10 34v-8h28v8"/></svg>;
  if (name === "chat") return <svg viewBox="0 0 48 48"><path d="M6 8h36v26H19L9 42v-8H6z"/><circle cx="17" cy="21" r="1"/><circle cx="24" cy="21" r="1"/><circle cx="31" cy="21" r="1"/></svg>;
  if (name === "cloud") return <svg viewBox="0 0 48 48"><path d="M13 37h25a8 8 0 0 0 1-16 13 13 0 0 0-25-3 10 10 0 0 0-1 19z"/></svg>;
  if (name === "vision") return <svg viewBox="0 0 48 48"><rect x="6" y="10" width="36" height="28" rx="4"/><circle cx="18" cy="21" r="4"/><path d="m9 34 9-8 6 5 6-7 9 10M24 4v6M24 38v6M2 24h4M42 24h4"/></svg>;
  return <svg viewBox="0 0 48 48"><rect x="8" y="13" width="32" height="27" rx="9"/><path d="M24 13V7M20 7h8M8 24H4M44 24h-4"/><circle cx="18" cy="26" r="2"/><circle cx="30" cy="26" r="2"/><path d="M18 33c4 3 8 3 12 0"/></svg>;
}

export function HomePage() {
  const { logout } = useAuth();
  const location = useLocation();
  const [agents, setAgents] = useState<Agent[]>([]);
  useEffect(() => { void api.listAgents().then(setAgents).catch(() => setAgents([])); }, []);
  const recent = useMemo(() => [...agents].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 3), [agents]);

  if (new URLSearchParams(location.search).has("edit")) return <Navigate to={`/agents${location.search}`} replace />;

  return <div className="app-shell home-shell">
    <AppHeader />
    <main className="home-content">
      <div className="home-intro"><div><h1>What would you like to build?</h1><p>Choose a workspace to get started.</p></div><div className="system-status"><span>All systems operational!</span><div className="system-runner" aria-hidden="true"><div className="runner-speed-lines"><i /><i /><i /><i /></div><div className="runner-body"><i /><div className="runner-base"><i /><b /></div></div></div></div></div>
      <section className="home-card-grid">
        {cards.map((card, index) => <Link className={`home-nav-card ${index === 0 ? "featured" : ""}`} to={card.to} key={card.to}>
          <CardIcon name={card.icon}/><span className="home-card-arrow">→</span><h2>{card.title}</h2><p>{card.description}</p>{index === 0 ? <small>{agents.length} agents</small> : null}
        </Link>)}
      </section>
      <section className="box recent-panel"><h2>Recent</h2>{recent.length ? recent.map((agent) => <Link key={agent.id} to={agent.agent_type === "normal" ? `/agents?edit=${agent.id}` : `/multi-agent?mode=${agent.agent_type}&edit=${agent.id}`}><strong>{agent.name}</strong><span className={`agent-type-badge ${agent.agent_type}`}>{agent.agent_type === "normal" ? "Agent" : agent.agent_type === "supervisor" ? "Supervisor" : "Router"}</span><small>{new Date(agent.updated_at).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</small><b>→</b></Link>) : <p>No recently edited agents yet.</p>}</section>
      <button className="home-signout" type="button" onClick={logout}><span aria-hidden="true">↪</span> Sign out</button>
    </main>
  </div>;
}
