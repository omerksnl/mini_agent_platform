import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, type Agent, type AgentInput, type Collection, type HttpTool, type Skill } from "../api";
import { useAuth } from "../AuthContext";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";
import { PromptVersionHistory } from "../components/PromptVersionHistory";

const emptyForm: AgentInput = {
  name: "",
  agent_type: "normal",
  system_prompt: "You are a helpful assistant.",
  model: DEFAULT_MODEL,
  temperature: 0.7,
  system_tools: ["calculator", "current_datetime"],
  tool_ids: [],
  skill_ids: [],
  collection_ids: [],
  managed_agent_ids: [],
  router_target_ids: [],
};

type PanelMode = "idle" | "create" | "edit";

export function AgentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { me, logout } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [form, setForm] = useState<AgentInput>(emptyForm);
  const [mode, setMode] = useState<PanelMode>("idle");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Agent | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function loadAgents() {
    setLoading(true);
    setError("");
    try {
      const [agentList, toolList, skillList, collectionList] = await Promise.all([api.listAgents(), api.listTools(), api.listSkills(), api.listCollections()]);
      setAgents(agentList);
      setTools(toolList);
      setSkills(skillList);
      setCollections(collectionList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAgents();
  }, []);

  useEffect(() => {
    const editId = searchParams.get("edit");
    const agent = agents.find((item) => item.id === editId && item.agent_type === "normal");
    if (agent) startEdit(agent);
  }, [agents, searchParams]);

  function closePanel() {
    setMode("idle");
    setEditingId(null);
    setForm(emptyForm);
    setError("");
    if (searchParams.has("edit")) setSearchParams({});
  }

  function startCreate() {
    setMode("create");
    setEditingId(null);
    setForm(emptyForm);
    setError("");
  }

  function startEdit(agent: Agent) {
    setMode("edit");
    setEditingId(agent.id);
    setForm({
      name: agent.name,
      agent_type: agent.agent_type,
      system_prompt: agent.system_prompt,
      model: agent.model,
      temperature: agent.temperature,
      system_tools: agent.system_tools,
      tool_ids: agent.tool_ids,
      skill_ids: agent.skill_ids,
      collection_ids: agent.collection_ids,
      managed_agent_ids: agent.managed_agent_ids,
      router_target_ids: agent.router_target_ids,
    });
    setError("");
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (mode === "edit" && editingId) {
        await api.updateAgent(editingId, form);
      } else {
        await api.createAgent(form);
      }
      closePanel();
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) {
      return;
    }
    setDeleting(true);
    setError("");
    try {
      await api.deleteAgent(pendingDelete.id);
      if (editingId === pendingDelete.id) {
        closePanel();
      }
      setPendingDelete(null);
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  const displayedAgents = [...agents].sort((left, right) => {
    const typeOrder = { supervisor: 0, router: 1, normal: 2 } as const;
    if (left.agent_type !== right.agent_type) return typeOrder[left.agent_type] - typeOrder[right.agent_type];
    return left.name.localeCompare(right.name);
  });

  return (
    <div className="app-shell">
      <header className="box topbar">
        <div>
          <p className="brand">Mini Agent</p>
          <p className="workspace">
            {me?.tenant_name} · {me?.user.full_name}
          </p>
        </div>
        <div className="topbar-actions">
          <Link className="btn btn-primary" to="/chat">Chat</Link>
          <Link className="btn" to="/tools">Tools</Link>
          <Link className="btn" to="/skills">Skills</Link>
          <Link className="btn" to="/collections">Collections</Link>
          <Link className="btn" to="/multi-agent">Multi-agent</Link>
          <Link className="btn" to="/workflows">Workflows</Link>
          <button type="button" className="btn" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="layout">
        <section className="box panel">
          <div className="panel-head">
            <h1>Agents</h1>
            <button type="button" className="btn btn-primary" onClick={startCreate}>New agent</button>
          </div>
          {loading ? <p>Loading...</p> : null}
          {!loading && agents.length === 0 ? (
            <p>No agents yet. Use New agent to create one.</p>
          ) : null}
          <ul className="agent-list agent-tree">
            {displayedAgents.map((agent) => (
              <li key={agent.id} className={`agent-tree-row ${editingId === agent.id ? "active" : ""}`}>
                {agent.agent_type !== "normal" ? <Link className="agent-item" to={`/multi-agent?mode=${agent.agent_type}&edit=${agent.id}`}>
                  <span className="agent-name-line"><strong>{agent.name}</strong><span className={`agent-type-badge ${agent.agent_type}`}>{agent.agent_type === "supervisor" ? "Supervisor" : "Router"}</span></span>
                  <span className="agent-meta">{agent.model} · t={agent.temperature}</span>
                </Link> : <button type="button" className="agent-item" onClick={() => startEdit(agent)}>
                  <span className="agent-name-line"><strong>{agent.name}</strong><span className="agent-type-badge">Agent</span></span>
                  <span className="agent-meta">{agent.model} · t={agent.temperature}</span>
                </button>}
                <button type="button" className="btn btn-danger" onClick={() => setPendingDelete(agent)}>Delete</button>
              </li>
            ))}
          </ul>
        </section>

        <section className="box panel">
          {mode === "idle" ? (
            <div className="idle-panel">
              <p className="idle-title">Start your journey here</p>
              <p>Create a new agent or select one to edit.</p>
            </div>
          ) : (
            <>
              <div className="panel-accent">
                <div className="panel-head">
                  <div>
                    <h1>{mode === "edit" ? "Edit agent" : "Create agent"}</h1>
                    <p>Type, model, instructions, capabilities, and managed agents.</p>
                  </div>
                  <button
                    type="button"
                    className="icon-close"
                    onClick={closePanel}
                    aria-label="Close"
                  >
                    ×
                  </button>
                </div>
              </div>
              {error ? <p className="error">{error}</p> : null}
              <form className="stack" onSubmit={onSubmit}>
                <label>
                  Name
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    required
                  />
                </label>
                <label>
                  Model
                  <select
                    value={form.model}
                    onChange={(e) => setForm({ ...form, model: e.target.value })}
                    required
                  >
                    {!MODEL_OPTIONS.some((option) => option.id === form.model) ? (
                      <option value={form.model}>{form.model} (existing)</option>
                    ) : null}
                    {MODEL_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label} · {option.provider}
                      </option>
                    ))}
                  </select>
                  <span className="field-hint">
                    Models available through the configured OpenRouter account.
                  </span>
                </label>
                <label>
                  Temperature ({form.temperature.toFixed(1)})
                  <span className="field-hint">
                    Lower is more focused and repeatable; higher is more varied.
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={2}
                    step={0.1}
                    value={form.temperature}
                    onChange={(e) =>
                      setForm({ ...form, temperature: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  System prompt
                  <textarea
                    rows={10}
                    value={form.system_prompt}
                    onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                  />
                </label>
                {mode === "edit" && editingId ? <PromptVersionHistory agentId={editingId} currentPrompt={form.system_prompt} onDraftCreated={(prompt) => setForm((current) => ({ ...current, system_prompt: prompt }))} onRestored={(agent) => {
                  setForm((current) => ({ ...current, system_prompt: agent.system_prompt }));
                  void loadAgents();
                }} /> : null}
                <fieldset className="tool-picker">
                  <legend>Tools</legend>
                  <span className="field-hint">The agent can only call selected tools.</span>
                  {[
                    { id: "calculator", description: "Safe arithmetic" },
                      { id: "current_datetime", description: "Current time by timezone" },
                      { id: "pdf_to_text", description: "Extract text from PDFs attached in chat" },
                      { id: "text_to_pdf", description: "Create a PDF using a safe registered template" },
                  ].map((tool) => (
                    <label className="tool-option" key={tool.id}>
                      <input
                        type="checkbox"
                        checked={form.system_tools.includes(tool.id)}
                        onChange={(event) => setForm({
                          ...form,
                          system_tools: event.target.checked
                            ? [...form.system_tools, tool.id]
                            : form.system_tools.filter((id) => id !== tool.id),
                        })}
                      />
                      <span><strong>{tool.id}</strong><small>{tool.description}</small></span>
                    </label>
                  ))}
                  {tools.map((tool) => (
                    <label className="tool-option" key={tool.id}>
                      <input
                        type="checkbox"
                        checked={form.tool_ids.includes(tool.id)}
                        onChange={(event) => setForm({
                          ...form,
                          tool_ids: event.target.checked
                            ? [...form.tool_ids, tool.id]
                            : form.tool_ids.filter((id) => id !== tool.id),
                        })}
                      />
                      <span><strong>{tool.name}</strong><small>{tool.description}</small></span>
                    </label>
                  ))}
                  {tools.length === 0 ? <Link className="field-hint" to="/tools">Create an HTTP tool</Link> : null}
                </fieldset>
                <fieldset className="tool-picker">
                  <legend>Knowledge collections</legend>
                  <span className="field-hint">Assigned collections give the agent a collection_search tool with source citations.</span>
                  {collections.map((collection) => (
                    <label className="tool-option" key={collection.id}>
                      <input type="checkbox" checked={form.collection_ids.includes(collection.id)} onChange={(event) => setForm({ ...form, collection_ids: event.target.checked ? [...form.collection_ids, collection.id] : form.collection_ids.filter((id) => id !== collection.id) })} />
                      <span><strong>{collection.name}</strong><small>{collection.documents.length} documents · {collection.description}</small></span>
                    </label>
                  ))}
                  {collections.length === 0 ? <Link className="field-hint" to="/collections">Create a collection</Link> : null}
                </fieldset>
                <fieldset className="tool-picker">
                  <legend>Skills</legend>
                  <span className="field-hint">Assigned skills are added to the agent system prompt in this order.</span>
                  {skills.filter((skill) => skill.is_active || form.skill_ids.includes(skill.id)).map((skill) => (
                    <label className="tool-option" key={skill.id}>
                      <input
                        type="checkbox"
                        checked={form.skill_ids.includes(skill.id)}
                        disabled={!skill.is_active}
                        onChange={(event) => setForm({
                          ...form,
                          skill_ids: event.target.checked
                            ? [...form.skill_ids, skill.id]
                            : form.skill_ids.filter((id) => id !== skill.id),
                        })}
                      />
                      <span><strong>{skill.name}</strong><small>{skill.description}{skill.is_active ? "" : " (inactive)"}</small></span>
                    </label>
                  ))}
                  {skills.length === 0 ? <Link className="field-hint" to="/skills">Create a skill</Link> : null}
                </fieldset>
                <button
                  type="submit"
                  className="btn btn-primary btn-large btn-block"
                  disabled={saving}
                >
                  {saving ? "Saving..." : mode === "edit" ? "Save changes" : "Create agent"}
                </button>
              </form>
            </>
          )}
        </section>
      </main>

      {pendingDelete ? (
        <div className="modal-backdrop" onClick={() => !deleting && setPendingDelete(null)}>
          <div
            className="box modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="delete-title">Delete agent</h2>
            <p>
              Remove <strong>{pendingDelete.name}</strong>? This cannot be undone.
              {pendingDelete.agent_type === "supervisor"
                ? " Its managed agents will remain as independent agents."
                : pendingDelete.agent_type === "router"
                  ? " Its target agents will remain as independent agents."
                  : ""}
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn"
                disabled={deleting}
                onClick={() => setPendingDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={deleting}
                onClick={() => void confirmDelete()}
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
