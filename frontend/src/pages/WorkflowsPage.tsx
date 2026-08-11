import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Agent, type AgentInput, type HttpTool, type Workflow, type WorkflowInput, type WorkflowRouteCondition, type WorkflowStepType } from "../api";
import { useAuth } from "../AuthContext";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";

type StepForm = { step_key: string; name: string; step_type: WorkflowStepType; target_id: string; system_tool_name: string; required_input: string; next_condition: WorkflowRouteCondition };
type Form = { name: string; description: string; is_active: boolean; steps: StepForm[] };
type ExecutionMode = "workflow" | "router" | "supervisor";
const blank: Form = { name: "", description: "", is_active: true, steps: [] };
const systemTools = ["calculator", "current_datetime", "pdf_to_text"];
const blankSupervisor: AgentInput = { name: "", agent_type: "supervisor", system_prompt: "You coordinate managed agents and delegate each task to the appropriate specialist.", model: DEFAULT_MODEL, temperature: 0.2, system_tools: [], tool_ids: [], skill_ids: [], collection_ids: [], managed_agent_ids: [] };

function createStep(index: number, agents: Agent[]): StepForm {
  return { step_key: `step_${index + 1}`, name: `Step ${index + 1}`, step_type: agents.length ? "agent" : "human_wait", target_id: agents[0]?.id ?? "", system_tool_name: "calculator", required_input: "", next_condition: "success" };
}

export function WorkflowsPage() {
  const { me, logout } = useAuth();
  const [items, setItems] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<HttpTool[]>([]);
  const [form, setForm] = useState<Form>(blank);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Workflow | null>(null);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("workflow");
  const [expandedSupervisors, setExpandedSupervisors] = useState<Set<string>>(new Set());
  const [showSupervisorForm, setShowSupervisorForm] = useState(false);
  const [supervisorForm, setSupervisorForm] = useState<AgentInput>(blankSupervisor);
  const [savingSupervisor, setSavingSupervisor] = useState(false);

  async function load() {
    setLoading(true); setError("");
    try {
      const [workflows, agentList, toolList] = await Promise.all([api.listWorkflows(), api.listAgents(), api.listTools()]);
      setItems(workflows); setAgents(agentList); setTools(toolList);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load workflows"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  function updateStep(index: number, patch: Partial<StepForm>) {
    setForm((current) => ({ ...current, steps: current.steps.map((step, i) => i === index ? { ...step, ...patch } : step) }));
  }
  function setStepType(index: number, type: WorkflowStepType) {
    updateStep(index, { step_type: type, target_id: type === "agent" ? agents[0]?.id ?? "" : type === "http_tool" ? tools[0]?.id ?? "" : "" });
  }
  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= form.steps.length) return;
    const steps = [...form.steps]; [steps[index], steps[target]] = [steps[target], steps[index]]; setForm({ ...form, steps });
  }
  function edit(workflow: Workflow) {
    const steps = [...workflow.steps].sort((a, b) => a.position - b.position);
    setEditingId(workflow.id);
    setForm({ name: workflow.name, description: workflow.description, is_active: workflow.is_active, steps: steps.map((step, index) => ({
      step_key: step.step_key, name: step.name, step_type: step.step_type,
      target_id: step.agent_id ?? step.http_tool_id ?? "", system_tool_name: step.system_tool_name ?? "calculator",
      required_input: typeof step.config.required_input === "string" ? step.config.required_input : "",
      next_condition: index < steps.length - 1 ? workflow.routes.find((route) => route.source_step_key === step.step_key)?.condition ?? "success" : "success",
    })) });
  }
  function payload(): WorkflowInput {
    const keys = form.steps.map((step) => step.step_key.trim());
    if (!keys.length) throw new Error("Add at least one workflow step");
    if (new Set(keys).size !== keys.length) throw new Error("Step keys must be unique");
    if (keys.some((key) => !/^[a-z][a-z0-9_]*$/.test(key))) throw new Error("Step keys must use lowercase letters, numbers, and underscores");
    return {
      name: form.name.trim(), description: form.description.trim(), is_active: form.is_active,
      steps: form.steps.map((step, position) => ({
        step_key: step.step_key.trim(), name: step.name.trim(), step_type: step.step_type, position,
        agent_id: step.step_type === "agent" ? step.target_id : null,
        http_tool_id: step.step_type === "http_tool" ? step.target_id : null,
        system_tool_name: step.step_type === "system_tool" ? step.system_tool_name : null,
        config: step.step_type === "human_wait" && step.required_input.trim() ? { required_input: step.required_input.trim() } : {},
      })),
      routes: form.steps.slice(0, -1).map((step, index) => ({ source_step_key: step.step_key.trim(), target_step_key: form.steps[index + 1].step_key.trim(), condition: step.next_condition, priority: 0, config: {} })),
    };
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try { const body = payload(); if (editingId) await api.updateWorkflow(editingId, body); else await api.createWorkflow(body); setEditingId(null); setForm(blank); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be saved"); }
    finally { setSaving(false); }
  }
  async function remove() {
    if (!pendingDelete) return;
    try { await api.deleteWorkflow(pendingDelete.id); if (editingId === pendingDelete.id) { setEditingId(null); setForm(blank); } setPendingDelete(null); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be deleted"); }
  }
  const open = editingId !== null || form.steps.length > 0;
  const supervisors = agents.filter((agent) => agent.agent_type === "supervisor");
  function selectMode(mode: ExecutionMode) {
    setExecutionMode(mode); setEditingId(null); setForm(blank); setError("");
  }
  function toggleSupervisor(id: string) {
    setExpandedSupervisors((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function createSupervisor(event: FormEvent) {
    event.preventDefault(); setSavingSupervisor(true); setError("");
    try { await api.createAgent({ ...supervisorForm, agent_type: "supervisor" }); setSupervisorForm(blankSupervisor); setShowSupervisorForm(false); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Supervisor could not be created"); }
    finally { setSavingSupervisor(false); }
  }

  return <div className="app-shell">
    <header className="box topbar"><div><p className="brand">Mini Agent</p><p className="workspace">{me?.tenant_name} · {me?.user.full_name}</p></div><div className="topbar-actions"><Link className="btn" to="/">Agents</Link><Link className="btn btn-primary" to="/multi-agent">Multi-agent</Link><Link className="btn" to="/chat">Chat</Link><button className="btn" onClick={logout}>Sign out</button></div></header>
    {error ? <p className="alert">{error}</p> : null}
    <section className="box execution-mode-panel">
      <div><h1>Multi-agent systems</h1><p>Choose how multiple agents coordinate for a task.</p></div>
      <div className="execution-mode-options">
        <button className={`execution-mode-card${executionMode === "workflow" ? " active" : ""}`} type="button" onClick={() => selectMode("workflow")}><strong>Workflow</strong><small>Runs predefined steps in a controlled order.</small></button>
        <button className={`execution-mode-card${executionMode === "router" ? " active" : ""}`} type="button" onClick={() => selectMode("router")}><strong>Router</strong><small>Selects an agent or workflow for each request.</small></button>
        <button className={`execution-mode-card${executionMode === "supervisor" ? " active" : ""}`} type="button" onClick={() => selectMode("supervisor")}><strong>Supervisor</strong><small>Coordinates managed agents dynamically.</small></button>
      </div>
    </section>
    {executionMode === "workflow" ? <main className="layout workflow-layout">
      <section className="box panel"><div className="panel-head"><h1>Workflow systems</h1><button className="btn btn-primary" onClick={() => { setEditingId(null); setForm({ ...blank, steps: [createStep(0, agents)] }); setError(""); }}>New multi-agent</button></div>
        {loading ? <p>Loading...</p> : !items.length ? <p>No workflows yet.</p> : <ul className="agent-list workflow-list">{items.map((item) => <li key={item.id}><button className={`agent-item${editingId === item.id ? " selected" : ""}`} onClick={() => edit(item)}><span><strong>{item.name}</strong><small>{item.steps.length} steps · {item.is_active ? "Active" : "Inactive"}</small></span></button><button className="btn btn-danger" onClick={() => setPendingDelete(item)}>Delete</button></li>)}</ul>}
      </section>
      <section className="box panel">{!open ? <div className="idle-panel"><p className="idle-title">Build a workflow</p><p>Create a workflow or select one to edit.</p></div> : <form className="stack" onSubmit={save}>
        <div className="panel-head"><h1>{editingId ? "Edit workflow" : "New workflow"}</h1><button type="button" className="icon-close" onClick={() => { setEditingId(null); setForm(blank); }}>×</button></div>
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Description<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="checkbox-line"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label>
        <div className="workflow-section-head"><h2>Steps</h2><button type="button" className="btn" onClick={() => setForm({ ...form, steps: [...form.steps, createStep(form.steps.length, agents)] })}>Add step</button></div>
        <div className="workflow-steps">{form.steps.map((step, index) => <div key={`${index}-${step.step_key}`}>
          <article className="workflow-step-editor"><div className="workflow-step-head"><strong>{index + 1}. {step.name || "Unnamed step"}</strong><div className="workflow-step-actions"><button type="button" className="btn btn-compact" disabled={!index} onClick={() => move(index, -1)}>Up</button><button type="button" className="btn btn-compact" disabled={index === form.steps.length - 1} onClick={() => move(index, 1)}>Down</button><button type="button" className="btn btn-danger btn-compact" onClick={() => setForm({ ...form, steps: form.steps.filter((_, i) => i !== index) })}>Remove</button></div></div>
            <div className="workflow-step-grid"><label>Step name<input required value={step.name} onChange={(e) => updateStep(index, { name: e.target.value })} /></label><label>Technical key<input required value={step.step_key} onChange={(e) => updateStep(index, { step_key: e.target.value })} /></label>
              <label>Step type<select value={step.step_type} onChange={(e) => setStepType(index, e.target.value as WorkflowStepType)}><option value="agent">Agent</option><option value="http_tool">HTTP tool</option><option value="system_tool">System tool</option><option value="human_wait">Human wait</option></select></label>
              {step.step_type === "agent" ? <label>Agent<select required value={step.target_id} onChange={(e) => updateStep(index, { target_id: e.target.value })}><option value="">Select an agent</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label> : null}
              {step.step_type === "http_tool" ? <label>HTTP tool<select required value={step.target_id} onChange={(e) => updateStep(index, { target_id: e.target.value })}><option value="">Select a tool</option>{tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}</select></label> : null}
              {step.step_type === "system_tool" ? <label>System tool<select value={step.system_tool_name} onChange={(e) => updateStep(index, { system_tool_name: e.target.value })}>{systemTools.map((tool) => <option key={tool}>{tool}</option>)}</select></label> : null}
              {step.step_type === "human_wait" ? <label>Required input<input placeholder="e.g. interview answers" value={step.required_input} onChange={(e) => updateStep(index, { required_input: e.target.value })} /></label> : null}
            </div></article>
          {index < form.steps.length - 1 ? <div className="workflow-route-preview"><span>↓</span><label>Continue when<select value={step.next_condition} onChange={(e) => updateStep(index, { next_condition: e.target.value as WorkflowRouteCondition })}><option value="success">Step succeeds</option><option value="failure">Step fails</option><option value="input_available">Input is available</option><option value="always">Always</option></select></label></div> : null}
        </div>)}</div>
        <div className="form-actions"><button type="button" className="btn" onClick={() => { setEditingId(null); setForm(blank); }}>Cancel</button><button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save workflow"}</button></div>
      </form>}</section>
    </main> : null}
    {executionMode === "router" ? <main className="box panel multi-agent-empty">
      <p className="idle-title">Router systems</p>
      <p>No routers yet. Router creation and routing rules will be added in the router feature.</p>
    </main> : null}
    {executionMode === "supervisor" ? <main className="box panel">
      <div className="panel-head"><div><h1>Supervisor systems</h1><p>Create supervisors here and open one to see its managed agents.</p></div><button className="btn btn-primary" type="button" onClick={() => setShowSupervisorForm(true)}>New supervisor</button></div>
      {showSupervisorForm ? <form className="stack supervisor-create-form" onSubmit={createSupervisor}>
        <div className="panel-head"><h2>New supervisor</h2><button type="button" className="icon-close" onClick={() => { setShowSupervisorForm(false); setSupervisorForm(blankSupervisor); }}>×</button></div>
        <div className="workflow-step-grid"><label>Name<input required value={supervisorForm.name} onChange={(event) => setSupervisorForm({ ...supervisorForm, name: event.target.value })} /></label><label>Model<select value={supervisorForm.model} onChange={(event) => setSupervisorForm({ ...supervisorForm, model: event.target.value })}>{MODEL_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label} · {option.provider}</option>)}</select></label></div>
        <label>Temperature ({supervisorForm.temperature.toFixed(1)})<input type="range" min={0} max={2} step={0.1} value={supervisorForm.temperature} onChange={(event) => setSupervisorForm({ ...supervisorForm, temperature: Number(event.target.value) })} /></label>
        <label>System prompt<textarea rows={6} required value={supervisorForm.system_prompt} onChange={(event) => setSupervisorForm({ ...supervisorForm, system_prompt: event.target.value })} /></label>
        <fieldset className="tool-picker"><legend>Managed agents</legend><span className="field-hint">Only available normal agents can be assigned.</span>{agents.filter((agent) => agent.agent_type === "normal" && agent.supervisor_id === null).map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={supervisorForm.managed_agent_ids.includes(agent.id)} onChange={(event) => setSupervisorForm({ ...supervisorForm, managed_agent_ids: event.target.checked ? [...supervisorForm.managed_agent_ids, agent.id] : supervisorForm.managed_agent_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name}</strong><small>{agent.model}</small></span></label>)}</fieldset>
        <div className="form-actions"><button className="btn" type="button" onClick={() => { setShowSupervisorForm(false); setSupervisorForm(blankSupervisor); }}>Cancel</button><button className="btn btn-primary" disabled={savingSupervisor}>{savingSupervisor ? "Saving..." : "Create supervisor"}</button></div>
      </form> : null}
      {loading ? <p>Loading...</p> : !supervisors.length ? <div className="multi-agent-empty"><p className="idle-title">No supervisors yet</p><p>Use New supervisor to create one.</p></div> : <ul className="supervisor-system-list">{supervisors.map((supervisor) => {
        const expanded = expandedSupervisors.has(supervisor.id);
        const managed = supervisor.managed_agent_ids.map((id) => agents.find((agent) => agent.id === id)).filter((agent): agent is Agent => Boolean(agent));
        return <li key={supervisor.id} className="supervisor-system">
          <button type="button" className="supervisor-system-head" onClick={() => toggleSupervisor(supervisor.id)} aria-expanded={expanded}>
            <span className={`tree-toggle ${expanded ? "expanded" : ""}`}><span aria-hidden="true" /></span>
            <span className="supervisor-summary"><strong>{supervisor.name}</strong><small>{managed.length} managed agents</small><small>{supervisor.model}</small></span>
            <span className="agent-type-badge supervisor">Supervisor</span>
          </button>
          {expanded ? <div className="supervisor-managed-area"><p className="managed-section-label">Managed agents</p><div className="supervisor-managed-grid">{managed.length ? managed.map((agent) => <article className="managed-agent-card" key={agent.id}><span className="agent-name-line"><strong>{agent.name}</strong><span className="agent-type-badge">Managed</span></span><span className="managed-agent-model">{agent.model}</span><small>Temperature: {agent.temperature}</small></article>) : <p>No managed agents</p>}</div></div> : null}
        </li>;
      })}</ul>}
    </main> : null}
    {pendingDelete ? <div className="modal-backdrop"><div className="box modal"><h2>Delete workflow?</h2><p><strong>{pendingDelete.name}</strong> and its step definition will be deleted.</p><div className="modal-actions"><button className="btn" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-danger" onClick={() => void remove()}>Delete</button></div></div></div> : null}
  </div>;
}
