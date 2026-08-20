import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type Agent, type AgentInput, type Collection, type HttpTool, type RemoteAgent, type Skill } from "../api";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";
import { PromptVersionHistory } from "../components/PromptVersionHistory";
import { A2APublishing } from "../components/A2APublishing";
import { AppHeader } from "../components/AppHeader";

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

type PanelMode = "idle" | "create" | "edit" | "remote";
type RemoteMessage = { role: "user" | "agent"; content: string; attachmentName?: string; apiCostUsd?: number };

export function AgentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [remoteAgents, setRemoteAgents] = useState<RemoteAgent[]>([]);
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
  const [showRemoteForm, setShowRemoteForm] = useState(false);
  const [remoteCardUrl, setRemoteCardUrl] = useState("");
  const [remoteApiKey, setRemoteApiKey] = useState("");
  const [savingRemote, setSavingRemote] = useState(false);
  const [selectedRemote, setSelectedRemote] = useState<RemoteAgent | null>(null);
  const [remoteDraft, setRemoteDraft] = useState("");
  const [remoteMessages, setRemoteMessages] = useState<RemoteMessage[]>([]);
  const [sendingRemote, setSendingRemote] = useState(false);
  const [remotePdf, setRemotePdf] = useState<File | null>(null);

  async function loadAgents() {
    setLoading(true);
    setError("");
    try {
      const [agentList, toolList, skillList, collectionList, remoteList] = await Promise.all([api.listAgents(), api.listTools(), api.listSkills(), api.listCollections(), api.listRemoteAgents()]);
      setAgents(agentList);
      setTools(toolList);
      setSkills(skillList);
      setCollections(collectionList);
      setRemoteAgents(remoteList);
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
    setSelectedRemote(null);
    setMode("create");
    setEditingId(null);
    setForm(emptyForm);
    setError("");
  }

  function startEdit(agent: Agent) {
    setSelectedRemote(null);
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

  async function connectRemote(event: FormEvent) {
    event.preventDefault();
    setSavingRemote(true);
    setError("");
    try {
      const remote = await api.createRemoteAgent(remoteCardUrl.trim(), remoteApiKey.trim());
      setRemoteAgents((current) => [remote, ...current]);
      setRemoteCardUrl("");
      setRemoteApiKey("");
      setShowRemoteForm(false);
      openRemote(remote);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remote agent could not be connected");
    } finally {
      setSavingRemote(false);
    }
  }

  function openRemote(remote: RemoteAgent) {
    setSelectedRemote(remote);
    setMode("remote");
    setEditingId(null);
    setRemoteMessages([]);
    setRemoteDraft("");
    setRemotePdf(null);
    setError("");
  }

  async function removeRemote(remote: RemoteAgent) {
    setError("");
    try {
      await api.deleteRemoteAgent(remote.id);
      setRemoteAgents((current) => current.filter((item) => item.id !== remote.id));
      if (selectedRemote?.id === remote.id) {
        setSelectedRemote(null);
        setMode("idle");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remote agent could not be removed");
    }
  }

  async function sendRemote(event: FormEvent) {
    event.preventDefault();
    const content = remoteDraft.trim();
    const pdf = remotePdf;
    if (!selectedRemote || (!content && !pdf) || sendingRemote) return;
    setRemoteDraft("");
    setRemotePdf(null);
    setSendingRemote(true);
    setError("");
    setRemoteMessages((current) => [...current, { role: "user", content, attachmentName: pdf?.name }]);
    try {
      const attachment = pdf ? await api.uploadAttachment(pdf) : null;
      const response = await api.sendRemoteAgentMessage(selectedRemote.id, content, attachment ? [attachment.id] : []);
      setRemoteMessages((current) => [...current, { role: "agent", content: response.content, apiCostUsd: response.api_cost_usd }]);
    } catch (err) {
      setRemoteDraft(content);
      setRemotePdf(pdf);
      setError(err instanceof Error ? err.message : "Remote agent request failed");
    } finally {
      setSendingRemote(false);
    }
  }

  function remoteEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const displayedAgents = [...agents].sort((left, right) => {
    const typeOrder = { supervisor: 0, router: 1, normal: 2 } as const;
    if (left.agent_type !== right.agent_type) return typeOrder[left.agent_type] - typeOrder[right.agent_type];
    return left.name.localeCompare(right.name);
  });
  const editingAgent = editingId ? agents.find((agent) => agent.id === editingId) ?? null : null;

  return (
    <div className="app-shell">
      <AppHeader />

      <main className="layout">
        <section className="box panel">
          <div className="panel-head">
            <h1>Agents</h1>
            <div className="panel-head-actions"><button type="button" className="btn" onClick={() => { setShowRemoteForm(true); setError(""); }}>Add remote</button><button type="button" className="btn btn-primary" onClick={startCreate}>New agent</button></div>
          </div>
          {loading ? <p>Loading...</p> : null}
          {!loading && agents.length === 0 ? (
            <p>No agents yet. Use New agent to create one.</p>
          ) : null}
          <div className="agent-section-label"><span>Local agents</span><strong>{displayedAgents.length}</strong></div>
          <ul className="agent-list agent-tree compact-agent-list">
            {displayedAgents.map((agent) => (
              <li key={agent.id} className={`agent-tree-row ${editingId === agent.id ? "active" : ""}`}>
                {agent.agent_type !== "normal" ? <Link className="agent-item" to={`/multi-agent?mode=${agent.agent_type}&edit=${agent.id}`}>
                  <span className="agent-name-line"><strong>{agent.name}</strong><span className={`agent-type-badge ${agent.agent_type}`}>{agent.agent_type === "supervisor" ? "Supervisor" : "Router"}</span></span>
                  <span className="agent-meta">{agent.model} · t={agent.temperature}</span>
                </Link> : <button type="button" className="agent-item" onClick={() => startEdit(agent)}>
                  <span className="agent-name-line"><strong>{agent.name}</strong><span className="agent-type-badge">Agent</span></span>
                  <span className="agent-meta">{agent.model} · t={agent.temperature}</span>
                </button>}
                <button type="button" className="agent-delete-compact" title={`Delete ${agent.name}`} aria-label={`Delete ${agent.name}`} onClick={() => setPendingDelete(agent)}>×</button>
              </li>
            ))}
          </ul>
          <div className="remote-agent-heading"><div><h2>Remote agents</h2><p>Agents connected through A2A.</p></div><span>{remoteAgents.length}</span></div>
          {remoteAgents.length ? <ul className="agent-list remote-agent-list">{remoteAgents.map((remote) => <li key={remote.id} className={selectedRemote?.id === remote.id ? "active" : ""}>
            <button type="button" className="agent-item" onClick={() => openRemote(remote)}><span className="agent-name-line"><strong>{remote.name}</strong><span className="agent-type-badge remote">A2A</span></span><span className="agent-meta">Remote · protocol {remote.protocol_version}</span></button>
            <button type="button" className="btn btn-danger" onClick={() => void removeRemote(remote)}>Remove</button>
          </li>)}</ul> : <p className="field-hint">Connect an Agent Card to use an agent published by another account.</p>}
        </section>

        <section className="box panel">
          {mode === "idle" ? (
            <div className="idle-panel">
              <p className="idle-title">Start your journey here</p>
              <p>Create a new agent or select one to edit.</p>
            </div>
          ) : mode === "remote" && selectedRemote ? (
            <div className="remote-agent-workspace">
              <div className="panel-accent"><div className="panel-head"><div><h1>{selectedRemote.name}</h1><p>Remote A2A agent · {selectedRemote.protocol_version}</p></div><button type="button" className="icon-close" onClick={() => { setSelectedRemote(null); setMode("idle"); }}>×</button></div></div>
              <div className="remote-agent-card-summary"><p>{selectedRemote.description}</p><div><span>Agent Card</span><code>{selectedRemote.agent_card_url}</code></div>{selectedRemote.skills.length ? <div className="remote-skill-list">{selectedRemote.skills.map((skill, index) => <span key={skill.id ?? index}>{skill.name ?? "Capability"}</span>)}</div> : null}</div>
              <div className="remote-message-thread">
                {!remoteMessages.length ? <div className="idle-panel"><p className="idle-title">Send a task through A2A</p><p>This message and any attached PDF are delivered to the remote account's agent.</p></div> : remoteMessages.map((message, index) => <div className={`remote-message ${message.role}`} key={`${message.role}-${index}`}><strong>{message.role === "user" ? "You" : selectedRemote.name}</strong>{message.attachmentName ? <span className="remote-pdf-chip">PDF · {message.attachmentName}</span> : null}{message.role === "agent" ? <><div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div><span className="remote-message-cost">API cost: ${Number(message.apiCostUsd ?? 0).toFixed(6)}</span></> : message.content ? <p>{message.content}</p> : null}</div>)}
                {sendingRemote ? <div className="remote-message agent"><strong>{selectedRemote.name}</strong><p>Working through A2A...</p></div> : null}
              </div>
              <form className="remote-composer" onSubmit={sendRemote}>
                <label className="remote-attach-button" title="Attach a PDF file" aria-label="Attach a PDF file">+
                  <input type="file" accept="application/pdf,.pdf" disabled={sendingRemote} onChange={(event) => { setRemotePdf(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} />
                </label>
                <div className="remote-composer-input">
                  <textarea rows={3} value={remoteDraft} onChange={(event) => setRemoteDraft(event.target.value)} onKeyDown={remoteEnter} placeholder="Send a task to this remote agent..." disabled={sendingRemote} />
                  {remotePdf ? <span className="pending-attachment">{remotePdf.name}<button type="button" onClick={() => setRemotePdf(null)} aria-label="Remove attachment">×</button></span> : null}
                </div>
                <button className="btn btn-primary btn-large" disabled={sendingRemote || (!remoteDraft.trim() && !remotePdf)}>{sendingRemote ? "Sending..." : "Send task"}</button>
              </form>
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
                {mode === "edit" && editingId ? <details className="agent-config-section"><summary><span>Prompt history & evaluation</span><small>Versions, scoring, and AI-assisted drafts</small></summary><div className="agent-config-content"><PromptVersionHistory agentId={editingId} currentPrompt={form.system_prompt} onDraftCreated={(prompt) => setForm((current) => ({ ...current, system_prompt: prompt }))} onRestored={(agent) => {
                  setForm((current) => ({ ...current, system_prompt: agent.system_prompt }));
                  void loadAgents();
                }} /></div></details> : null}
                {editingAgent ? <details className="agent-config-section"><summary><span>A2A publishing</span><small>Expose this agent securely to other platforms</small></summary><div className="agent-config-content"><A2APublishing agent={editingAgent} onChanged={loadAgents} /></div></details> : null}
                <details className="agent-config-section"><summary><span>Capabilities & knowledge</span><small>{form.system_tools.length + form.tool_ids.length} tools · {form.skill_ids.length} skills · {form.collection_ids.length} collections</small></summary><div className="agent-config-content capability-config-grid">
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
                </div></details>
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
      {showRemoteForm ? <div className="modal-backdrop" onClick={() => !savingRemote && setShowRemoteForm(false)}><form className="box modal remote-connect-modal" onSubmit={connectRemote} onClick={(event) => event.stopPropagation()}><h2>Connect remote A2A agent</h2><p>Paste the Agent Card URL and the API key supplied by the publishing account.</p><label>Agent Card URL<input type="url" required value={remoteCardUrl} onChange={(event) => setRemoteCardUrl(event.target.value)} placeholder="https://example.com/a2a/agents/.../.well-known/agent-card.json" /></label><label>A2A API key<input type="password" required value={remoteApiKey} onChange={(event) => setRemoteApiKey(event.target.value)} placeholder="a2a_..." /></label><span className="field-hint">The card is verified without calling the model. The API key is encrypted before storage.</span><div className="modal-actions"><button type="button" className="btn" disabled={savingRemote} onClick={() => setShowRemoteForm(false)}>Cancel</button><button className="btn btn-primary" disabled={savingRemote}>{savingRemote ? "Connecting..." : "Connect agent"}</button></div></form></div> : null}
    </div>
  );
}
