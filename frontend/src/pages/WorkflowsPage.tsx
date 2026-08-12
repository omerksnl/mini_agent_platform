import { useEffect, useState, type DragEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Agent, type AgentInput, type Workflow, type WorkflowInput, type WorkflowRouteCondition, type WorkflowRun, type WorkflowStepType } from "../api";
import { useAuth } from "../AuthContext";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";

type StepForm = { step_key: string; name: string; step_type: WorkflowStepType; target_id: string; system_tool_name: string; required_input: string; next_condition: WorkflowRouteCondition };
type Form = { name: string; description: string; is_active: boolean; steps: StepForm[] };
type ExecutionMode = "workflow" | "router" | "supervisor";
const blank: Form = { name: "", description: "", is_active: true, steps: [] };
const blankSupervisor: AgentInput = { name: "", agent_type: "supervisor", system_prompt: "You coordinate managed agents and delegate each task to the appropriate specialist.", model: DEFAULT_MODEL, temperature: 0.2, system_tools: [], tool_ids: [], skill_ids: [], collection_ids: [], managed_agent_ids: [] };

function RelationshipArrows({ count, id, twoWay = false }: { count: number; id: string; twoWay?: boolean }) {
  return <svg className="relationship-arrows" viewBox="0 0 100 60" preserveAspectRatio="none" aria-hidden="true">
    <title>{id}</title>
    {Array.from({ length: count }, (_, index) => {
      const targetX = (index + 0.5) * (100 / count);
      return <g key={index}>
        <line x1="50" y1="3" x2={targetX} y2="57" />
        {twoWay ? <polygon points="48.8,4.5 51.2,4.5 50,0" /> : null}
        <polygon points={`${targetX - 1.2},55.5 ${targetX + 1.2},55.5 ${targetX},60`} />
      </g>;
    })}
  </svg>;
}

function createStep(index: number, agents: Agent[]): StepForm {
  const agent = agents.find((item) => item.agent_type === "normal");
  return { step_key: `step_${index + 1}`, name: agent?.name ?? `Human input ${index + 1}`, step_type: agent ? "agent" : "human_wait", target_id: agent?.id ?? "", system_tool_name: "", required_input: "", next_condition: "success" };
}

export function WorkflowsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { me, logout } = useAuth();
  const [items, setItems] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [form, setForm] = useState<Form>(blank);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showWorkflowForm, setShowWorkflowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Workflow | null>(null);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("workflow");
  const [expandedSupervisors, setExpandedSupervisors] = useState<Set<string>>(new Set());
  const [showSupervisorForm, setShowSupervisorForm] = useState(false);
  const [supervisorForm, setSupervisorForm] = useState<AgentInput>(blankSupervisor);
  const [savingSupervisor, setSavingSupervisor] = useState(false);
  const [editingSupervisorId, setEditingSupervisorId] = useState<string | null>(null);
  const [runWorkflow, setRunWorkflow] = useState<Workflow | null>(null);
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);
  const [runInput, setRunInput] = useState("");
  const [humanInput, setHumanInput] = useState("");
  const [running, setRunning] = useState(false);

  async function load() {
    setLoading(true); setError("");
    try {
      const [workflows, agentList] = await Promise.all([api.listWorkflows(), api.listAgents()]);
      setItems(workflows); setAgents(agentList);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load workflows"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (searchParams.get("mode") !== "supervisor") return;
    setExecutionMode("supervisor");
    const supervisor = agents.find((item) => item.id === searchParams.get("edit") && item.agent_type === "supervisor");
    if (supervisor) {
      setEditingSupervisorId(supervisor.id); setShowSupervisorForm(true);
      setSupervisorForm({ name: supervisor.name, agent_type: "supervisor", system_prompt: supervisor.system_prompt, model: supervisor.model, temperature: supervisor.temperature, system_tools: supervisor.system_tools, tool_ids: supervisor.tool_ids, skill_ids: supervisor.skill_ids, collection_ids: supervisor.collection_ids, managed_agent_ids: supervisor.managed_agent_ids });
    }
  }, [agents, searchParams]);

  function updateStep(index: number, patch: Partial<StepForm>) {
    setForm((current) => ({ ...current, steps: current.steps.map((step, i) => i === index ? { ...step, ...patch } : step) }));
  }
  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= form.steps.length) return;
    const steps = [...form.steps]; [steps[index], steps[target]] = [steps[target], steps[index]]; setForm({ ...form, steps });
  }
  function dropWorkflowNode(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const kind = event.dataTransfer.getData("application/x-workflow-node");
    if (kind === "human_wait") {
      const index = form.steps.length;
      setForm({ ...form, steps: [...form.steps, { ...createStep(index, []), step_key: `human_wait_${index + 1}`, name: "Human wait", step_type: "human_wait" }] });
      return;
    }
    const agent = agents.find((item) => item.id === kind && item.agent_type === "normal");
    if (!agent) return;
    const index = form.steps.length;
    setForm({ ...form, steps: [...form.steps, { ...createStep(index, agents), step_key: `agent_${index + 1}`, name: agent.name, target_id: agent.id }] });
  }
  function edit(workflow: Workflow) {
    const steps = [...workflow.steps].sort((a, b) => a.position - b.position);
    setEditingId(workflow.id);
    setShowWorkflowForm(true);
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
    try { const body = payload(); if (editingId) await api.updateWorkflow(editingId, body); else await api.createWorkflow(body); setEditingId(null); setShowWorkflowForm(false); setForm(blank); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be saved"); }
    finally { setSaving(false); }
  }
  async function remove() {
    if (!pendingDelete) return;
    try { await api.deleteWorkflow(pendingDelete.id); if (editingId === pendingDelete.id) { setEditingId(null); setForm(blank); } setPendingDelete(null); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be deleted"); }
  }
  const open = showWorkflowForm;
  const supervisors = agents.filter((agent) => agent.agent_type === "supervisor");
  const routerTargets = agents.filter((agent) => agent.agent_type === "normal").slice(0, 3);
  function selectMode(mode: ExecutionMode) {
    setExecutionMode(mode); setEditingId(null); setShowWorkflowForm(false); setForm(blank); setError(""); setSearchParams(mode === "supervisor" ? { mode } : {});
  }
  function toggleSupervisor(id: string) {
    setExpandedSupervisors((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function createSupervisor(event: FormEvent) {
    event.preventDefault(); setSavingSupervisor(true); setError("");
    try { if (editingSupervisorId) await api.updateAgent(editingSupervisorId, { ...supervisorForm, agent_type: "supervisor" }); else await api.createAgent({ ...supervisorForm, agent_type: "supervisor" }); setSupervisorForm(blankSupervisor); setEditingSupervisorId(null); setShowSupervisorForm(false); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Supervisor could not be created"); }
    finally { setSavingSupervisor(false); }
  }
  function openSupervisorEditor(supervisor: Agent) {
    setEditingSupervisorId(supervisor.id); setShowSupervisorForm(true);
    setSupervisorForm({ name: supervisor.name, agent_type: "supervisor", system_prompt: supervisor.system_prompt, model: supervisor.model, temperature: supervisor.temperature, system_tools: supervisor.system_tools, tool_ids: supervisor.tool_ids, skill_ids: supervisor.skill_ids, collection_ids: supervisor.collection_ids, managed_agent_ids: supervisor.managed_agent_ids });
    setSearchParams({ mode: "supervisor", edit: supervisor.id });
  }
  function openRunner(workflow: Workflow) {
    setRunWorkflow(workflow); setActiveRun(null); setRunInput(""); setHumanInput(""); setEditingId(null); setForm(blank); setError("");
  }
  async function startRun(event: FormEvent) {
    event.preventDefault(); if (!runWorkflow) return; setRunning(true); setError("");
    try { setActiveRun(await api.startWorkflowRun(runWorkflow.id, { request: runInput.trim() })); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be started"); }
    finally { setRunning(false); }
  }
  async function resumeRun(event: FormEvent) {
    event.preventDefault(); if (!activeRun) return; setRunning(true); setError("");
    try { setActiveRun(await api.resumeWorkflowRun(activeRun.id, { response: humanInput.trim() })); setHumanInput(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Workflow could not be resumed"); }
    finally { setRunning(false); }
  }
  const completedSteps = activeRun?.step_runs.filter((step) => step.status === "completed").length ?? 0;
  const progress = runWorkflow ? Math.round((completedSteps / runWorkflow.steps.length) * 100) : 0;

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
      <section className="box panel"><div className="panel-head"><h1>Workflow systems</h1><button className="btn btn-primary" onClick={() => { setEditingId(null); setShowWorkflowForm(true); setForm(blank); setError(""); }}>New multi-agent</button></div>
        {loading ? <p>Loading...</p> : !items.length ? <p>No workflows yet.</p> : <ul className="agent-list workflow-list">{items.map((item) => <li key={item.id}><button className={`agent-item${editingId === item.id || runWorkflow?.id === item.id ? " selected" : ""}`} onClick={() => edit(item)}><span><strong>{item.name}</strong><small>{item.steps.length} steps · {item.is_active ? "Active" : "Inactive"}</small></span></button><div className="workflow-list-actions"><button className="btn btn-primary btn-compact" disabled={!item.is_active} onClick={() => openRunner(item)}>Run</button><button className="btn btn-danger btn-compact" onClick={() => setPendingDelete(item)}>Delete</button></div></li>)}</ul>}
      </section>
      <section className="box panel">{runWorkflow ? <div className="stack workflow-run-panel">
        <div className="panel-head"><div><h1>{runWorkflow.name}</h1><p>Run and monitor this workflow.</p></div><button type="button" className="icon-close" onClick={() => { setRunWorkflow(null); setActiveRun(null); }}>×</button></div>
        {!activeRun ? <form className="stack" onSubmit={startRun}><label>Initial request<textarea rows={5} required placeholder="Describe the task and provide the initial workflow input." value={runInput} onChange={(event) => setRunInput(event.target.value)} /></label><button className="btn btn-primary" disabled={running}>{running ? "Starting..." : "Start workflow"}</button></form> : <>
          <div className={`workflow-run-summary status-${activeRun.status}`}><span><strong>{activeRun.status === "waiting" ? "Waiting for human input" : activeRun.status}</strong><small>{completedSteps} of {runWorkflow.steps.length} steps completed</small></span><strong>{progress}%</strong></div>
          <div className="workflow-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>
          <ol className="workflow-run-steps">{[...runWorkflow.steps].sort((a, b) => a.position - b.position).map((definition) => { const stepRun = activeRun.step_runs.find((step) => step.step_key === definition.step_key); const status = stepRun?.status ?? "pending"; return <li className={`run-step status-${status}`} key={definition.id}><span className="run-step-marker" /><span><strong>{definition.name}</strong><small>{definition.step_type.replace("_", " ")} · {status}</small>{stepRun?.error ? <small className="run-step-error">{stepRun.error}</small> : null}</span>{stepRun?.api_cost_usd ? <small>${stepRun.api_cost_usd.toFixed(6)}</small> : null}</li>; })}</ol>
          {activeRun.status === "waiting" ? <form className="human-wait-form" onSubmit={resumeRun}><label>Required human input<textarea rows={4} required value={humanInput} onChange={(event) => setHumanInput(event.target.value)} placeholder="Enter approval, interview answers, or the requested information." /></label><button className="btn btn-primary" disabled={running}>{running ? "Continuing..." : "Continue workflow"}</button></form> : null}
          {activeRun.status === "failed" ? <p className="alert">{activeRun.error}</p> : null}
          {activeRun.status === "completed" ? <div className="workflow-result"><strong>Workflow completed</strong><pre>{JSON.stringify(activeRun.output_data.last_output ?? activeRun.output_data, null, 2)}</pre></div> : null}
          <p className="workflow-run-cost">API cost: ${activeRun.total_api_cost_usd.toFixed(6)}</p>
        </>}
      </div> : !open ? <div className="idle-panel"><p className="idle-title">Build a workflow</p><p>Create a workflow or select one to edit.</p></div> : <form className="stack" onSubmit={save}>
        <div className="panel-head"><h1>{editingId ? "Edit workflow" : "New workflow"}</h1><button type="button" className="icon-close" onClick={() => { setEditingId(null); setShowWorkflowForm(false); setForm(blank); }}>×</button></div>
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Description<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="checkbox-line"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label>
        <div className="workflow-builder">
          <aside className="workflow-palette"><h2>Agent list</h2><p>Drag nodes into the workflow.</p>{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <div className="palette-node" draggable onDragStart={(event) => { event.dataTransfer.setData("application/x-workflow-node", agent.id); event.dataTransfer.effectAllowed = "copy"; }} key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small></div>)}<div className="palette-node human" draggable onDragStart={(event) => { event.dataTransfer.setData("application/x-workflow-node", "human_wait"); event.dataTransfer.effectAllowed = "copy"; }}><strong>Human wait</strong><small>Pause for user input</small></div></aside>
          <div className={`workflow-canvas${form.steps.length ? " has-nodes" : ""}`} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDrop={dropWorkflowNode}>
            {!form.steps.length ? <div className="workflow-drop-empty"><strong>Drag the first node here</strong><span>Agent or Human wait</span></div> : form.steps.map((step, index) => { const selectedAgent = agents.find((agent) => agent.id === step.target_id); return <div className="compact-flow-segment" key={`${index}-${step.step_key}`}><article className={`compact-graph-node ${step.step_type === "human_wait" ? "human" : ""}`}><span className="compact-node-number">{index + 1}</span><strong>{step.step_type === "human_wait" ? "Human wait" : selectedAgent?.name ?? step.name}</strong><small>{step.step_type === "human_wait" ? <input aria-label="Required human input" required placeholder="Required input" value={step.required_input} onChange={(event) => updateStep(index, { required_input: event.target.value })} /> : selectedAgent?.model}</small><div className="compact-node-actions"><button type="button" disabled={!index} onClick={() => move(index, -1)}>↑</button><button type="button" disabled={index === form.steps.length - 1} onClick={() => move(index, 1)}>↓</button><button type="button" onClick={() => setForm({ ...form, steps: form.steps.filter((_, i) => i !== index) })}>×</button></div></article>{index < form.steps.length - 1 ? <div className="compact-flow-edge"><span /><select aria-label="Route condition" value={step.next_condition} onChange={(event) => updateStep(index, { next_condition: event.target.value as WorkflowRouteCondition })}><option value="success">success</option><option value="failure">failure</option><option value="input_available">input available</option><option value="always">always</option></select></div> : null}</div>; })}
            {form.steps.length ? <p className="drop-more-hint">Drop another node anywhere in this canvas to append it.</p> : null}
          </div>
        </div>
        <div className="form-actions"><button type="button" className="btn" onClick={() => { setEditingId(null); setShowWorkflowForm(false); setForm(blank); }}>Cancel</button><button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save workflow"}</button></div>
      </form>}</section>
    </main> : null}
    {executionMode === "router" ? <main className="box panel">
      <div className="panel-head"><div><h1>Router systems</h1><p>A router selects exactly one agent for each request.</p></div></div>
      <div className="multi-agent-empty"><div className="relationship-graph router-preview"><div className="relationship-root"><strong>Router</strong><small>No router configured</small></div>{routerTargets.length ? <RelationshipArrows count={routerTargets.length} id="router" /> : null}<div className="relationship-children">{routerTargets.map((agent) => <Link to={`/?edit=${agent.id}`} className="relationship-node" key={agent.id}><strong>{agent.name}</strong><small>Possible target</small></Link>)}</div></div><p>Router creation and routing rules will be added in the router feature.</p></div>
    </main> : null}
    {executionMode === "supervisor" ? <main className="box panel">
      <div className="panel-head"><div><h1>Supervisor systems</h1><p>Create supervisors here and open one to see its managed agents.</p></div><button className="btn btn-primary" type="button" onClick={() => { setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setShowSupervisorForm(true); setSearchParams({ mode: "supervisor" }); }}>New supervisor</button></div>
      {showSupervisorForm ? <form className="stack supervisor-create-form" onSubmit={createSupervisor}>
        <div className="panel-head"><h2>{editingSupervisorId ? "Edit supervisor" : "New supervisor"}</h2><button type="button" className="icon-close" onClick={() => { setShowSupervisorForm(false); setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setSearchParams({ mode: "supervisor" }); }}>×</button></div>
        <div className="workflow-step-grid"><label>Name<input required value={supervisorForm.name} onChange={(event) => setSupervisorForm({ ...supervisorForm, name: event.target.value })} /></label><label>Model<select value={supervisorForm.model} onChange={(event) => setSupervisorForm({ ...supervisorForm, model: event.target.value })}>{MODEL_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label} · {option.provider}</option>)}</select></label></div>
        <label>Temperature ({supervisorForm.temperature.toFixed(1)})<input type="range" min={0} max={2} step={0.1} value={supervisorForm.temperature} onChange={(event) => setSupervisorForm({ ...supervisorForm, temperature: Number(event.target.value) })} /></label>
        <label>System prompt<textarea rows={6} required value={supervisorForm.system_prompt} onChange={(event) => setSupervisorForm({ ...supervisorForm, system_prompt: event.target.value })} /></label>
        <fieldset className="tool-picker"><legend>Managed agents</legend><span className="field-hint">Normal agents can be reused by multiple supervisors.</span>{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={supervisorForm.managed_agent_ids.includes(agent.id)} onChange={(event) => setSupervisorForm({ ...supervisorForm, managed_agent_ids: event.target.checked ? [...supervisorForm.managed_agent_ids, agent.id] : supervisorForm.managed_agent_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name}</strong><small>{agent.model}</small></span></label>)}</fieldset>
        <div className="form-actions"><button className="btn" type="button" onClick={() => { setShowSupervisorForm(false); setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setSearchParams({ mode: "supervisor" }); }}>Cancel</button><button className="btn btn-primary" disabled={savingSupervisor}>{savingSupervisor ? "Saving..." : editingSupervisorId ? "Save supervisor" : "Create supervisor"}</button></div>
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
          {expanded ? <div className="supervisor-managed-area"><div className="relationship-graph supervisor-graph"><button type="button" className="relationship-root editable" onClick={() => openSupervisorEditor(supervisor)}><strong>{supervisor.name}</strong><small>Supervisor · click to edit</small></button>{managed.length ? <><RelationshipArrows count={managed.length} id={supervisor.id} twoWay /><div className="relationship-children">{managed.map((agent) => <Link to={`/?edit=${agent.id}`} className="relationship-node" key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small><span>Click to edit</span></Link>)}</div></> : <p>No managed agents</p>}</div></div> : null}
        </li>;
      })}</ul>}
    </main> : null}
    {pendingDelete ? <div className="modal-backdrop"><div className="box modal"><h2>Delete workflow?</h2><p><strong>{pendingDelete.name}</strong> and its step definition will be deleted.</p><div className="modal-actions"><button className="btn" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-danger" onClick={() => void remove()}>Delete</button></div></div></div> : null}
  </div>;
}
