import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type Agent, type AgentInput, type AgentProviderAssignment, type Collection, type Guardrail, type HttpTool, type ProviderCredential, type RemoteAgent, type Skill } from "../api";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";
import { PromptVersionHistory } from "../components/PromptVersionHistory";
import { A2APublishing } from "../components/A2APublishing";
import { AppHeader } from "../components/AppHeader";
import { SingleAgentWorkspaceHeader } from "../components/SingleAgentWorkspaceHeader";

const emptyForm: AgentInput = {
  name: "",
  agent_type: "normal",
  system_prompt: "You are a helpful assistant.",
  model: DEFAULT_MODEL,
  temperature: 0.7,
  collection_search_limit: 5,
  system_tools: ["calculator", "current_datetime"],
  tool_ids: [],
  skill_ids: [],
  collection_ids: [],
  guardrail_ids: [],
  managed_agent_ids: [],
  router_target_ids: [],
  managed_remote_agent_ids: [],
  router_remote_agent_ids: [],
  remote_agent_ids: [],
};

type PanelMode = "idle" | "create" | "edit" | "remote";
type RemoteMessage = { role: "user" | "agent"; content: string; attachmentName?: string; apiCostUsd?: number; billedTo?: "agent_owner" | "caller"; provider?: "openrouter" | "openai" | null };

export function AgentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [remoteAgents, setRemoteAgents] = useState<RemoteAgent[]>([]);
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [guardrails, setGuardrails] = useState<Guardrail[]>([]);
  const [providerProfiles, setProviderProfiles] = useState<ProviderCredential[]>([]);
  const [providerAssignments, setProviderAssignments] = useState<AgentProviderAssignment[]>([]);
  const [selectedProviderProfile, setSelectedProviderProfile] = useState("");
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
  const [remoteBillingMode, setRemoteBillingMode] = useState<"owner" | "caller">("owner");
  const [remoteProviderProfile, setRemoteProviderProfile] = useState("");
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
      const [agentList, toolList, skillList, collectionList, guardrailList, remoteList, profileList, assignmentList] = await Promise.all([api.listAgents(), api.listTools(), api.listSkills(), api.listCollections(), api.listGuardrails(), api.listRemoteAgents(), api.listProviderCredentials(), api.listAgentProviderAssignments()]);
      setAgents(agentList);
      setTools(toolList);
      setSkills(skillList);
      setCollections(collectionList);
      setGuardrails(guardrailList);
      setRemoteAgents(remoteList);
      setProviderProfiles(profileList);
      setProviderAssignments(assignmentList);
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
    setSelectedProviderProfile("");
    setError("");
    if (searchParams.has("edit")) setSearchParams({});
  }

  function startCreate() {
    setSelectedRemote(null);
    setMode("create");
    setEditingId(null);
    setForm(emptyForm);
    setSelectedProviderProfile("");
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
      collection_search_limit: agent.collection_search_limit,
      system_tools: agent.system_tools,
      tool_ids: agent.tool_ids,
      skill_ids: agent.skill_ids,
      collection_ids: agent.collection_ids,
      guardrail_ids: agent.guardrail_ids,
      managed_agent_ids: agent.managed_agent_ids,
      router_target_ids: agent.router_target_ids,
      managed_remote_agent_ids: agent.managed_remote_agent_ids,
      router_remote_agent_ids: agent.router_remote_agent_ids,
      remote_agent_ids: agent.remote_agent_ids,
    });
    setSelectedProviderProfile(providerAssignments.find((item) => item.agent_id === agent.id)?.credential_id ?? "");
    setError("");
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      let savedAgent: Agent;
      if (mode === "edit" && editingId) {
        savedAgent = await api.updateAgent(editingId, form);
      } else {
        savedAgent = await api.createAgent(form);
      }
      await api.setAgentProviderAssignment(savedAgent.id, selectedProviderProfile || null);
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
      const remote = await api.createRemoteAgent(
        remoteCardUrl.trim(),
        remoteApiKey.trim(),
        remoteBillingMode,
        remoteBillingMode === "caller" ? remoteProviderProfile : null,
      );
      setRemoteAgents((current) => [remote, ...current]);
      setRemoteCardUrl("");
      setRemoteApiKey("");
      setRemoteBillingMode("owner");
      setRemoteProviderProfile("");
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
      setRemoteMessages((current) => [...current, { role: "agent", content: response.content, apiCostUsd: response.api_cost_usd, billedTo: response.billed_to, provider: response.provider }]);
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
      <SingleAgentWorkspaceHeader />

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
            <button type="button" className="agent-item" onClick={() => openRemote(remote)}><span className="agent-name-line"><strong>{remote.name}</strong><span className="agent-type-badge remote">A2A</span></span><span className="agent-meta">Remote · {remote.billing_mode === "caller" ? "You pay" : "Owner pays"} · protocol {remote.protocol_version}</span></button>
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
              <div className="remote-agent-card-summary"><p>{selectedRemote.description}</p><div><span>Agent Card</span><code>{selectedRemote.agent_card_url}</code></div><div className={`a2a-billing-badge ${selectedRemote.billing_mode}`}><strong>{selectedRemote.billing_mode === "caller" ? "Caller pays" : "Agent owner pays"}</strong><span>{selectedRemote.billing_mode === "caller" ? "Uses your selected provider profile without exposing its API key." : "The publishing account covers model usage."}</span></div>{selectedRemote.skills.length ? <div className="remote-skill-list">{selectedRemote.skills.map((skill, index) => <span key={skill.id ?? index}>{skill.name ?? "Capability"}</span>)}</div> : null}</div>
              <div className="remote-message-thread">
                {!remoteMessages.length ? <div className="idle-panel"><p className="idle-title">Send a task through A2A</p><p>This message and any attached PDF are delivered to the remote account's agent.</p></div> : remoteMessages.map((message, index) => <div className={`remote-message ${message.role}`} key={`${message.role}-${index}`}><strong>{message.role === "user" ? "You" : selectedRemote.name}</strong>{message.attachmentName ? <span className="remote-pdf-chip">PDF · {message.attachmentName}</span> : null}{message.role === "agent" ? <><div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div><span className="remote-message-cost">API cost: ${Number(message.apiCostUsd ?? 0).toFixed(6)} · {message.billedTo === "caller" ? "Billed to you" : "Billed to agent owner"}{message.provider ? ` · ${message.provider === "openai" ? "OpenAI" : "OpenRouter"}` : ""}</span></> : message.content ? <p>{message.content}</p> : null}</div>)}
                {sendingRemote ? <div className="remote-message agent"><strong>{selectedRemote.name}</strong><p>Working through A2A...</p></div> : null}
              </div>
              {error ? <p className="error remote-agent-error" role="alert">{error}</p> : null}
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
                  AI provider profile
                  <select value={selectedProviderProfile} onChange={(event) => setSelectedProviderProfile(event.target.value)}>
                    <option value="">Inherit my active provider</option>
                    {providerProfiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {profile.name} · {profile.provider === "openai" ? "OpenAI" : "OpenRouter"}
                      </option>
                    ))}
                  </select>
                  <span className="field-hint">This choice is private to your account, even when the agent is shared inside the tenant.</span>
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
                  Collection search results
                  <span className="field-hint">
                    Maximum collection chunks supplied to this agent per search.
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={form.collection_search_limit}
                    onChange={(event) => setForm({
                      ...form,
                      collection_search_limit: Number(event.target.value),
                    })}
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
                <details className="agent-config-section"><summary><span>Capabilities, knowledge & safety</span><small>{form.system_tools.length + form.tool_ids.length} tools · {form.skill_ids.length} skills · {form.collection_ids.length} collections · {form.guardrail_ids.length} guardrails</small></summary><div className="agent-config-content capability-config-grid">
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
                  <legend>Remote A2A agents</legend>
                  <span className="field-hint">Selected remote specialists become callable tools for this agent.</span>
                  {remoteAgents.map((remote) => (
                    <label className="tool-option" key={remote.id}>
                      <input type="checkbox" checked={form.remote_agent_ids.includes(remote.id)} onChange={(event) => setForm({ ...form, remote_agent_ids: event.target.checked ? [...form.remote_agent_ids, remote.id] : form.remote_agent_ids.filter((id) => id !== remote.id) })} />
                      <span><strong>{remote.name} · A2A</strong><small>{remote.description || "Remote specialist"}</small></span>
                    </label>
                  ))}
                  {remoteAgents.length === 0 ? <span className="field-hint">Connect a remote agent from the Agents list first.</span> : null}
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
                <fieldset className="tool-picker">
                  <legend>Guardrails</legend>
                  <span className="field-hint">Policies run locally before or after the model call.</span>
                  {guardrails.filter((item) => item.is_active || form.guardrail_ids.includes(item.id)).map((item) => (
                    <label className="tool-option" key={item.id}>
                      <input type="checkbox" checked={form.guardrail_ids.includes(item.id)} disabled={!item.is_active} onChange={(event) => setForm({ ...form, guardrail_ids: event.target.checked ? [...form.guardrail_ids, item.id] : form.guardrail_ids.filter((id) => id !== item.id) })} />
                      <span><strong>{item.name}</strong><small>{item.guardrail_type.replaceAll("_", " ")} · {item.stages.join(", ")}{item.is_active ? "" : " (inactive)"}</small></span>
                    </label>
                  ))}
                  {guardrails.length === 0 ? <Link className="field-hint" to="/guardrails">Create a guardrail</Link> : null}
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
      {showRemoteForm ? <div className="modal-backdrop" onClick={() => !savingRemote && setShowRemoteForm(false)}><form className="box modal remote-connect-modal" onSubmit={connectRemote} onClick={(event) => event.stopPropagation()}><h2>Connect remote A2A agent</h2><p>Paste the Agent Card URL and the API key supplied by the publishing account.</p><label>Agent Card URL<input type="url" required value={remoteCardUrl} onChange={(event) => setRemoteCardUrl(event.target.value)} placeholder="https://example.com/a2a/agents/.../.well-known/agent-card.json" /></label><label>A2A API key<input type="password" required value={remoteApiKey} onChange={(event) => setRemoteApiKey(event.target.value)} placeholder="a2a_..." /></label><fieldset className="a2a-billing-picker"><legend>Who pays for model usage?</legend><label><input type="radio" name="billing" checked={remoteBillingMode === "owner"} onChange={() => setRemoteBillingMode("owner")} /><span><strong>Agent owner</strong><small>The publishing account's provider pays.</small></span></label><label><input type="radio" name="billing" checked={remoteBillingMode === "caller"} onChange={() => setRemoteBillingMode("caller")} /><span><strong>Use my provider profile</strong><small>Available for accounts on this Mini Agent deployment.</small></span></label></fieldset>{remoteBillingMode === "caller" ? <label>Provider profile<select required value={remoteProviderProfile} onChange={(event) => setRemoteProviderProfile(event.target.value)}><option value="">Select a saved API key</option>{providerProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.provider === "openai" ? "OpenAI" : "OpenRouter"}</option>)}</select></label> : null}<span className="field-hint">Provider keys stay encrypted and are never included in A2A requests or responses.</span><div className="modal-actions"><button type="button" className="btn" disabled={savingRemote} onClick={() => setShowRemoteForm(false)}>Cancel</button><button className="btn btn-primary" disabled={savingRemote || (remoteBillingMode === "caller" && !remoteProviderProfile)}>{savingRemote ? "Connecting..." : "Connect agent"}</button></div></form></div> : null}
    </div>
  );
}
