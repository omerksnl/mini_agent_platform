import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Agent, type AgentInput, type AgentProviderAssignment, type ProviderCredential, type RemoteAgent, type Workflow, type WorkflowInput, type WorkflowRouteCondition, type WorkflowRun, type WorkflowStepType } from "../api";
import { DEFAULT_MODEL, MODEL_OPTIONS } from "../modelOptions";
import { PromptVersionHistory } from "../components/PromptVersionHistory";
import { HumanFeedback } from "../components/HumanFeedback";
import { A2APublishing } from "../components/A2APublishing";
import { AppHeader } from "../components/AppHeader";

type CollectionMode = "off" | "search" | "full_context";
type StepForm = { step_key: string; name: string; step_type: WorkflowStepType; target_id: string; system_tool_name: string; required_input: string; task_instructions: string; collection_mode: CollectionMode; input_artifact_keys: string; max_output_tokens: string; report_input_key: string; report_template_id: "blank_markdown" | "two_column"; report_filename: string; report_title: string; next_condition: WorkflowRouteCondition };
type Form = { name: string; description: string; is_active: boolean; steps: StepForm[] };
type ExecutionMode = "workflow" | "router" | "supervisor";
const blank: Form = { name: "", description: "", is_active: true, steps: [] };
const blankSupervisor: AgentInput = { name: "", agent_type: "supervisor", system_prompt: "You coordinate managed agents and delegate each task to the appropriate specialist.", model: DEFAULT_MODEL, temperature: 0.2, system_tools: [], tool_ids: [], skill_ids: [], collection_ids: [], managed_agent_ids: [], router_target_ids: [], managed_remote_agent_ids: [], router_remote_agent_ids: [], remote_agent_ids: [] };
const blankRouter: AgentInput = { name: "", agent_type: "router", system_prompt: "Route each request to exactly one suitable specialist. Ask one short clarification question only when the request is genuinely ambiguous.", model: DEFAULT_MODEL, temperature: 0.1, system_tools: [], tool_ids: [], skill_ids: [], collection_ids: [], managed_agent_ids: [], router_target_ids: [], managed_remote_agent_ids: [], router_remote_agent_ids: [], remote_agent_ids: [] };

function readableLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function structuredMarkdown(value: unknown, depth = 2): string {
  if (value === null || value === undefined) return "_None_";
  if (Array.isArray(value)) {
    if (!value.length) return "_None_";
    return value.map((item, index) => item && typeof item === "object"
      ? `${"#".repeat(Math.min(depth, 6))} ${index + 1}\n\n${structuredMarkdown(item, depth + 1)}`
      : `- ${typeof item === "boolean" ? item ? "Yes" : "No" : String(item)}`
    ).join("\n\n");
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return "_None_";
    return entries.map(([key, item]) => `${"#".repeat(Math.min(depth, 6))} ${readableLabel(key)}\n\n${structuredMarkdown(item, depth + 1)}`).join("\n\n");
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function markdownFromString(value: string): string {
  const trimmed = value.trim();
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try { return structuredMarkdown(JSON.parse(trimmed)); } catch { return value; }
  }
  return value;
}

function ArtifactContent({ data }: { data: Record<string, unknown> }) {
  if (typeof data.download_url === "string") {
    const filename = typeof data.filename === "string" ? data.filename : "workflow-report.pdf";
    return <div className="workflow-generated-file"><p><strong>{filename}</strong></p><p>{typeof data.template_id === "string" ? readableLabel(data.template_id) : "PDF report"}</p><button type="button" className="btn btn-primary" onClick={() => api.downloadGeneratedFile(data.download_url as string, filename)}>Download PDF</button></div>;
  }
  const humanInput = data.human_input && typeof data.human_input === "object"
    ? data.human_input as Record<string, unknown>
    : null;
  const content = typeof data.content === "string"
    ? data.content
    : typeof data.result === "string"
      ? data.result
      : typeof humanInput?.response === "string"
        ? humanInput.response
        : null;
  const markdown = content ? markdownFromString(content) : structuredMarkdown(data);
  return <div className="markdown-content workflow-artifact-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown></div>;
}

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
  return { step_key: `step_${index + 1}`, name: agent?.name ?? `Human input ${index + 1}`, step_type: agent ? "agent" : "human_wait", target_id: agent?.id ?? "", system_tool_name: "", required_input: "", task_instructions: "", collection_mode: "search", input_artifact_keys: "", max_output_tokens: "", report_input_key: "", report_template_id: "two_column", report_filename: "{candidate_name}-assessment.pdf", report_title: "Final Candidate Assessment", next_condition: agent ? "success" : "input_available" };
}

function artifactKeyFor(name: string, existing: StepForm[]): string {
  const base = name.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "agent";
  let key = base;
  let suffix = 2;
  while (existing.some((step) => step.step_key === key)) key = `${base}_${suffix++}`;
  return key;
}

export function WorkflowsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [remoteAgents, setRemoteAgents] = useState<RemoteAgent[]>([]);
  const [providerProfiles, setProviderProfiles] = useState<ProviderCredential[]>([]);
  const [providerAssignments, setProviderAssignments] = useState<AgentProviderAssignment[]>([]);
  const [selectedProviderProfile, setSelectedProviderProfile] = useState("");
  const [form, setForm] = useState<Form>(blank);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showWorkflowForm, setShowWorkflowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Workflow | null>(null);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("router");
  const [expandedSupervisors, setExpandedSupervisors] = useState<Set<string>>(new Set());
  const [showSupervisorForm, setShowSupervisorForm] = useState(false);
  const [supervisorForm, setSupervisorForm] = useState<AgentInput>(blankSupervisor);
  const [savingSupervisor, setSavingSupervisor] = useState(false);
  const [editingSupervisorId, setEditingSupervisorId] = useState<string | null>(null);
  const [expandedRouters, setExpandedRouters] = useState<Set<string>>(new Set());
  const [showRouterForm, setShowRouterForm] = useState(false);
  const [routerForm, setRouterForm] = useState<AgentInput>(blankRouter);
  const [savingRouter, setSavingRouter] = useState(false);
  const [editingRouterId, setEditingRouterId] = useState<string | null>(null);
  const [runWorkflow, setRunWorkflow] = useState<Workflow | null>(null);
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);
  const [runInput, setRunInput] = useState("");
  const [humanInput, setHumanInput] = useState("");
  const [running, setRunning] = useState(false);
  const [pendingWorkflowFile, setPendingWorkflowFile] = useState<File | null>(null);
  const [selectedStepIndex, setSelectedStepIndex] = useState<number | null>(null);
  const pollSequence = useRef(0);

  async function load() {
    setLoading(true); setError("");
    try {
      const [workflows, agentList, remoteList, profileList, assignmentList] = await Promise.all([api.listWorkflows(), api.listAgents(), api.listRemoteAgents(), api.listProviderCredentials(), api.listAgentProviderAssignments()]);
      setItems(workflows); setAgents(agentList); setRemoteAgents(remoteList); setProviderProfiles(profileList); setProviderAssignments(assignmentList);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load workflows"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!activeRun || activeRun.status !== "running") return;
    let cancelled = false;
    const refresh = async () => {
      const sequence = ++pollSequence.current;
      try {
        const next = await api.getWorkflowRun(activeRun.id);
        if (!cancelled && sequence === pollSequence.current) setActiveRun(next);
      } catch { /* Retry on the next polling interval. */ }
    };
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 750);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeRun?.id, activeRun?.status]);
  useEffect(() => {
    const mode = searchParams.get("mode");
    if (mode === "supervisor") {
      setExecutionMode("supervisor");
      const supervisor = agents.find((item) => item.id === searchParams.get("edit") && item.agent_type === "supervisor");
      if (supervisor) {
        setEditingSupervisorId(supervisor.id); setShowSupervisorForm(true);
        setSupervisorForm({ name: supervisor.name, agent_type: "supervisor", system_prompt: supervisor.system_prompt, model: supervisor.model, temperature: supervisor.temperature, system_tools: supervisor.system_tools, tool_ids: supervisor.tool_ids, skill_ids: supervisor.skill_ids, collection_ids: supervisor.collection_ids, managed_agent_ids: supervisor.managed_agent_ids, router_target_ids: [], managed_remote_agent_ids: supervisor.managed_remote_agent_ids, router_remote_agent_ids: [], remote_agent_ids: [] });
        setSelectedProviderProfile(providerAssignments.find((item) => item.agent_id === supervisor.id)?.credential_id ?? "");
      }
    } else if (mode === "router") {
      setExecutionMode("router");
      const router = agents.find((item) => item.id === searchParams.get("edit") && item.agent_type === "router");
      if (router) openRouterEditor(router);
    }
  }, [agents, providerAssignments, searchParams]);

  function updateStep(index: number, patch: Partial<StepForm>) {
    setForm((current) => ({ ...current, steps: current.steps.map((step, i) => i === index ? { ...step, ...patch } : step) }));
  }
  function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= form.steps.length) return;
    const steps = [...form.steps]; [steps[index], steps[target]] = [steps[target], steps[index]]; setForm({ ...form, steps }); setSelectedStepIndex(null);
  }
  function dropWorkflowNode(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const kind = event.dataTransfer.getData("application/x-workflow-node");
    if (kind === "human_wait") {
      const index = form.steps.length;
      setForm({ ...form, steps: [...form.steps, {
        ...createStep(index, []),
        step_key: artifactKeyFor("human_wait", form.steps),
        name: "Human wait",
        step_type: "human_wait",
      }] });
      return;
    }
    if (kind === "report") {
      const index = form.steps.length;
      setForm({ ...form, steps: [...form.steps, {
        ...createStep(index, []),
        step_key: artifactKeyFor("pdf_report", form.steps),
        name: "PDF report",
        step_type: "report",
        report_input_key: form.steps.at(-1)?.step_key ?? "",
        next_condition: "success",
      }] });
      return;
    }
    const agent = agents.find((item) => item.id === kind && item.agent_type === "normal");
    if (!agent) return;
    const index = form.steps.length;
    setForm({ ...form, steps: [...form.steps, { ...createStep(index, agents), step_key: artifactKeyFor(agent.name, form.steps), name: agent.name, target_id: agent.id }] });
  }
  function edit(workflow: Workflow) {
    const steps = [...workflow.steps].sort((a, b) => a.position - b.position);
    setEditingId(workflow.id);
    setShowWorkflowForm(true);
    setForm({ name: workflow.name, description: workflow.description, is_active: workflow.is_active, steps: steps.map((step, index) => ({
      step_key: step.step_key, name: step.name, step_type: step.step_type,
      target_id: step.agent_id ?? step.remote_agent_id ?? step.http_tool_id ?? "", system_tool_name: step.system_tool_name ?? "calculator",
      required_input: typeof step.config.required_input === "string" ? step.config.required_input : "",
      task_instructions: typeof step.config.task_instructions === "string" ? step.config.task_instructions : "",
      collection_mode: step.config.collection_mode === "off" || step.config.collection_mode === "search" || step.config.collection_mode === "full_context"
        ? step.config.collection_mode
        : step.config.use_collections === false ? "off" : "search",
      input_artifact_keys: Array.isArray(step.config.input_artifact_keys) ? step.config.input_artifact_keys.join(", ") : "",
      max_output_tokens: typeof step.config.max_output_tokens === "number" ? String(step.config.max_output_tokens) : "",
      report_input_key: typeof step.config.input_artifact_key === "string" ? step.config.input_artifact_key : "",
      report_template_id: step.config.template_id === "blank_markdown" ? "blank_markdown" : "two_column",
      report_filename: typeof step.config.filename === "string" ? step.config.filename : "{candidate_name}-assessment.pdf",
      report_title: typeof step.config.title === "string" ? step.config.title : "Final Candidate Assessment",
      next_condition: step.step_type === "human_wait" ? "input_available" : index < steps.length - 1 ? workflow.routes.find((route) => route.source_step_key === step.step_key)?.condition ?? "success" : "success",
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
        remote_agent_id: step.step_type === "remote_agent" ? step.target_id : null,
        http_tool_id: step.step_type === "http_tool" ? step.target_id : null,
        system_tool_name: step.step_type === "system_tool" ? step.system_tool_name : null,
        config: step.step_type === "human_wait"
          ? step.required_input.trim() ? { required_input: step.required_input.trim() } : {}
          : step.step_type === "agent"
            ? {
                task_instructions: step.task_instructions.trim(),
                collection_mode: step.collection_mode,
                use_collections: step.collection_mode !== "off",
                input_artifact_keys: step.input_artifact_keys.split(",").map((key) => key.trim()).filter(Boolean),
                ...(step.max_output_tokens ? { max_output_tokens: Number(step.max_output_tokens) } : {}),
              }
            : step.step_type === "report"
              ? {
                  input_artifact_key: step.report_input_key.trim(),
                  template_id: step.report_template_id,
                  filename: step.report_filename.trim(),
                  ...(step.report_title.trim() ? { title: step.report_title.trim() } : {}),
                }
            : {},
      })),
      routes: form.steps.slice(0, -1).map((step, index) => ({ source_step_key: step.step_key.trim(), target_step_key: form.steps[index + 1].step_key.trim(), condition: step.step_type === "human_wait" ? "input_available" : step.next_condition, priority: 0, config: {} })),
    };
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try { const body = payload(); if (editingId) await api.updateWorkflow(editingId, body); else await api.createWorkflow(body); setEditingId(null); setSelectedStepIndex(null); setShowWorkflowForm(false); setForm(blank); await load(); }
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
  const routers = agents.filter((agent) => agent.agent_type === "router");
  function selectMode(mode: ExecutionMode) {
    setExecutionMode(mode); setEditingId(null); setShowWorkflowForm(false); setForm(blank); setError(""); setSearchParams(mode === "supervisor" || mode === "router" ? { mode } : {});
  }
  function toggleSupervisor(id: string) {
    setExpandedSupervisors((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function createSupervisor(event: FormEvent) {
    event.preventDefault(); setSavingSupervisor(true); setError("");
    try { const saved = editingSupervisorId ? await api.updateAgent(editingSupervisorId, { ...supervisorForm, agent_type: "supervisor" }) : await api.createAgent({ ...supervisorForm, agent_type: "supervisor" }); await api.setAgentProviderAssignment(saved.id, selectedProviderProfile || null); setSupervisorForm(blankSupervisor); setSelectedProviderProfile(""); setEditingSupervisorId(null); setShowSupervisorForm(false); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Supervisor could not be created"); }
    finally { setSavingSupervisor(false); }
  }
  function openSupervisorEditor(supervisor: Agent) {
    setEditingSupervisorId(supervisor.id); setShowSupervisorForm(true);
    setSupervisorForm({ name: supervisor.name, agent_type: "supervisor", system_prompt: supervisor.system_prompt, model: supervisor.model, temperature: supervisor.temperature, system_tools: supervisor.system_tools, tool_ids: supervisor.tool_ids, skill_ids: supervisor.skill_ids, collection_ids: supervisor.collection_ids, managed_agent_ids: supervisor.managed_agent_ids, router_target_ids: [], managed_remote_agent_ids: supervisor.managed_remote_agent_ids, router_remote_agent_ids: [], remote_agent_ids: [] });
    setSelectedProviderProfile(providerAssignments.find((item) => item.agent_id === supervisor.id)?.credential_id ?? "");
    setSearchParams({ mode: "supervisor", edit: supervisor.id });
  }
  function toggleRouter(id: string) {
    setExpandedRouters((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  async function saveRouter(event: FormEvent) {
    event.preventDefault(); setSavingRouter(true); setError("");
    try { const saved = editingRouterId ? await api.updateAgent(editingRouterId, { ...routerForm, agent_type: "router" }) : await api.createAgent({ ...routerForm, agent_type: "router" }); await api.setAgentProviderAssignment(saved.id, selectedProviderProfile || null); setRouterForm(blankRouter); setSelectedProviderProfile(""); setEditingRouterId(null); setShowRouterForm(false); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Router could not be saved"); }
    finally { setSavingRouter(false); }
  }
  function openRouterEditor(router: Agent) {
    setEditingRouterId(router.id); setShowRouterForm(true);
    setRouterForm({ name: router.name, agent_type: "router", system_prompt: router.system_prompt, model: router.model, temperature: router.temperature, system_tools: [], tool_ids: [], skill_ids: [], collection_ids: [], managed_agent_ids: [], router_target_ids: router.router_target_ids, managed_remote_agent_ids: [], router_remote_agent_ids: router.router_remote_agent_ids, remote_agent_ids: [] });
    setSelectedProviderProfile(providerAssignments.find((item) => item.agent_id === router.id)?.credential_id ?? "");
    setSearchParams({ mode: "router", edit: router.id });
  }
  function openRunner(workflow: Workflow) {
    setRunWorkflow(workflow); setActiveRun(null); setRunInput(""); setHumanInput(""); setPendingWorkflowFile(null); setEditingId(null); setForm(blank); setError("");
  }
  async function startRun(event: FormEvent) {
    event.preventDefault(); if (!runWorkflow) return; setRunning(true); setError("");
    try {
      const attachment = pendingWorkflowFile ? await api.uploadAttachment(pendingWorkflowFile) : null;
      setActiveRun(await api.startWorkflowRun(runWorkflow.id, { request: runInput.trim() }, attachment ? [attachment.id] : []));
      setPendingWorkflowFile(null);
    }
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
  const waitingStep = activeRun?.current_step_id
    ? (runWorkflow?.steps ?? []).find((step) => "id" in step && step.id === activeRun.current_step_id)
    : null;
  const requiredHumanInput = typeof waitingStep?.config.required_input === "string" && waitingStep.config.required_input.trim()
    ? waitingStep.config.required_input.trim()
    : "Required human input";
  const editingRouter = editingRouterId ? agents.find((agent) => agent.id === editingRouterId) ?? null : null;
  const editingSupervisor = editingSupervisorId ? agents.find((agent) => agent.id === editingSupervisorId) ?? null : null;

  return <div className="app-shell">
    <AppHeader />
    {error ? <p className="alert">{error}</p> : null}
    <section className="box execution-mode-panel">
      <div><h1>Multi-agent systems</h1><p>Choose how multiple agents coordinate for a task.</p></div>
      <div className="execution-mode-options">
        <button className={`execution-mode-card${executionMode === "router" ? " active" : ""}`} type="button" onClick={() => selectMode("router")}><strong>Router</strong><small>Selects exactly one normal agent for each request.</small></button>
        <button className={`execution-mode-card${executionMode === "supervisor" ? " active" : ""}`} type="button" onClick={() => selectMode("supervisor")}><strong>Supervisor</strong><small>Coordinates managed agents dynamically.</small></button>
      </div>
    </section>
    {executionMode === "workflow" ? <main className="layout workflow-layout">
      <section className="box panel"><div className="panel-head"><h1>Workflow systems</h1><button className="btn btn-primary" onClick={() => { setEditingId(null); setShowWorkflowForm(true); setForm(blank); setError(""); }}>New multi-agent</button></div>
        {loading ? <p>Loading...</p> : !items.length ? <p>No workflows yet.</p> : <ul className="agent-list workflow-list">{items.map((item) => <li key={item.id}><button className={`agent-item${editingId === item.id || runWorkflow?.id === item.id ? " selected" : ""}`} onClick={() => edit(item)}><span><strong>{item.name}</strong><small>{item.steps.length} steps · {item.is_active ? "Active" : "Inactive"}</small></span></button><div className="workflow-list-actions"><button className="btn btn-primary btn-compact" disabled={!item.is_active} onClick={() => openRunner(item)}>Run</button><button className="btn btn-danger btn-compact" onClick={() => setPendingDelete(item)}>Delete</button></div></li>)}</ul>}
      </section>
      <section className="box panel">{runWorkflow ? <div className="stack workflow-run-panel">
        <div className="panel-head"><div><h1>{runWorkflow.name}</h1><p>Run and monitor this workflow.</p></div><button type="button" className="icon-close" onClick={() => { setRunWorkflow(null); setActiveRun(null); }}>×</button></div>
        {!activeRun ? <form className="stack" onSubmit={startRun}><label>Initial request<textarea rows={5} required placeholder="Describe the task and provide the initial workflow input." value={runInput} onChange={(event) => setRunInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !running) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /></label><div className="workflow-run-attachment"><label className="btn attachment-button">Attach PDF<input type="file" accept="application/pdf,.pdf" disabled={running} onChange={(event) => setPendingWorkflowFile(event.target.files?.[0] ?? null)} /></label>{pendingWorkflowFile ? <span className="pending-attachment">{pendingWorkflowFile.name}<button type="button" onClick={() => setPendingWorkflowFile(null)} aria-label="Remove attachment">×</button></span> : <small>Optional. The first PDF-capable agent can extract it.</small>}</div><button className="btn btn-primary" disabled={running}>{running ? pendingWorkflowFile ? "Uploading PDF..." : "Starting..." : "Start workflow"}</button></form> : <>
          <div className={`workflow-run-summary status-${activeRun.status}`}><span><strong>{activeRun.status === "waiting" ? "Waiting for human input" : activeRun.status}</strong><small>{completedSteps} of {runWorkflow.steps.length} steps completed</small></span><strong>{progress}%</strong></div>
          <div className="workflow-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>
          {activeRun.artifacts.length ? <section className="workflow-artifact-previews">{activeRun.artifacts.map((artifact) => <details className="workflow-artifact-preview" key={`preview-${artifact.id}`}><summary><span><strong>{artifact.name}</strong><small>{artifact.artifact_key} · {artifact.artifact_type.replace("_", " ")}</small></span><span className="artifact-toggle-label">View</span></summary><div className="workflow-artifact-scroll"><ArtifactContent data={artifact.data} /></div></details>)}</section> : null}
          <ol className="workflow-run-steps">{[...runWorkflow.steps].sort((a, b) => a.position - b.position).map((definition) => { const stepRun = activeRun.step_runs.find((step) => step.step_key === definition.step_key); const status = stepRun?.status ?? "pending"; return <li className={`run-step status-${status}`} key={definition.id}><span className="run-step-marker" /><span><strong>{definition.name}</strong><small>{definition.step_type.replace("_", " ")} · {status}</small>{stepRun?.error ? <small className="run-step-error">{stepRun.error}</small> : null}</span>{stepRun?.api_cost_usd ? <small>${stepRun.api_cost_usd.toFixed(6)}</small> : null}</li>; })}</ol>
          {activeRun.artifacts.length ? <section className="workflow-artifacts"><div className="workflow-artifacts-head"><strong>Artifacts</strong><span>{activeRun.artifacts.length}</span></div>{activeRun.artifacts.map((artifact) => <details className="workflow-artifact" key={artifact.id}><summary><span><strong>{artifact.name}</strong><small>{artifact.artifact_key} · {artifact.artifact_type.replace("_", " ")}</small></span><span>View</span></summary><pre>{JSON.stringify(artifact.data, null, 2)}</pre></details>)}</section> : null}
          {activeRun.status === "waiting" ? <form className="human-wait-form" onSubmit={resumeRun}><label>{requiredHumanInput}<textarea rows={4} required value={humanInput} onChange={(event) => setHumanInput(event.target.value)} placeholder={requiredHumanInput} /></label><button className="btn btn-primary" disabled={running}>{running ? "Continuing..." : "Continue workflow"}</button></form> : null}
          {activeRun.status === "failed" ? <p className="alert">{activeRun.error}</p> : null}
          {activeRun.status === "completed" ? <details className="workflow-result"><summary><strong>Final output</strong><span className="artifact-toggle-label">View</span></summary><div className="workflow-artifact-scroll"><ArtifactContent data={(activeRun.output_data.last_output ?? activeRun.output_data) as Record<string, unknown>} /></div></details> : null}
          {activeRun.status === "completed" ? <HumanFeedback targetType="workflow_run" targetId={activeRun.id} /> : null}
          <p className="workflow-run-cost">API cost: ${activeRun.total_api_cost_usd.toFixed(6)}</p>
        </>}
      </div> : !open ? <div className="idle-panel"><p className="idle-title">Build a workflow</p><p>Create a workflow or select one to edit.</p></div> : <form className="stack" onSubmit={save}>
        <div className="panel-head"><h1>{editingId ? "Edit workflow" : "New workflow"}</h1><button type="button" className="icon-close" onClick={() => { setEditingId(null); setShowWorkflowForm(false); setForm(blank); }}>×</button></div>
        <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>Description<textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="checkbox-line"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active</label>
        <div className="workflow-builder">
          <aside className="workflow-palette"><h2>Node list</h2><p>Drag nodes into the workflow.</p>{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <div className="palette-node" draggable onDragStart={(event) => { event.dataTransfer.setData("application/x-workflow-node", agent.id); event.dataTransfer.effectAllowed = "copy"; }} key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small></div>)}<div className="palette-node human" draggable onDragStart={(event) => { event.dataTransfer.setData("application/x-workflow-node", "human_wait"); event.dataTransfer.effectAllowed = "copy"; }}><strong>Human wait</strong><small>Pause for user input</small></div><div className="palette-node report" draggable onDragStart={(event) => { event.dataTransfer.setData("application/x-workflow-node", "report"); event.dataTransfer.effectAllowed = "copy"; }}><strong>PDF report</strong><small>Render an artifact without an LLM call</small></div></aside>
          <div className={`workflow-canvas${form.steps.length ? " has-nodes" : ""}`} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDrop={dropWorkflowNode}>
            {!form.steps.length ? <div className="workflow-drop-empty"><strong>Drag the first node here</strong><span>Agent, Human wait, or PDF report</span></div> : form.steps.map((step, index) => { const selectedAgent = agents.find((agent) => agent.id === step.target_id); return <div className="compact-flow-segment" key={`${index}-${step.step_key}`}><article className={`compact-graph-node ${step.step_type === "human_wait" ? "human" : step.step_type === "report" ? "report" : ""}`}><span className="compact-node-number">{index + 1}</span><strong>{step.step_type === "human_wait" ? "Human wait" : step.step_type === "report" ? "PDF report" : selectedAgent?.name ?? step.name}</strong><small>{step.step_type === "human_wait" ? <input aria-label="Required human input" required placeholder="Required input" value={step.required_input} onChange={(event) => updateStep(index, { required_input: event.target.value })} /> : step.step_type === "report" ? readableLabel(step.report_template_id) : selectedAgent?.model}</small><div className="compact-node-actions"><button type="button" className="compact-edit-action" onClick={() => setSelectedStepIndex(index)}>Edit</button><button type="button" disabled={!index} onClick={() => move(index, -1)}>↑</button><button type="button" disabled={index === form.steps.length - 1} onClick={() => move(index, 1)}>↓</button><button type="button" onClick={() => { setForm({ ...form, steps: form.steps.filter((_, i) => i !== index) }); setSelectedStepIndex(null); }}>×</button></div></article>{index < form.steps.length - 1 ? <div className="compact-flow-edge"><span /><select aria-label="Route condition" value={step.next_condition} onChange={(event) => updateStep(index, { next_condition: event.target.value as WorkflowRouteCondition })}><option value="success">success</option><option value="failure">failure</option><option value="input_available">input available</option><option value="always">always</option></select></div> : null}</div>; })}
            {form.steps.length ? <p className="drop-more-hint">Drop another node anywhere in this canvas to append it.</p> : null}
          </div>
        </div>
        {selectedStepIndex !== null && form.steps[selectedStepIndex] ? <section className="workflow-node-settings"><div className="panel-head"><div><h2>Node settings</h2><p>Configure this workflow stage.</p></div><button type="button" className="icon-close" onClick={() => setSelectedStepIndex(null)}>×</button></div><div className="workflow-step-grid"><label>Artifact name<input required maxLength={255} value={form.steps[selectedStepIndex].name} onChange={(event) => updateStep(selectedStepIndex, { name: event.target.value })} /></label><label>Artifact key<input required maxLength={64} pattern="[a-z][a-z0-9_]*" value={form.steps[selectedStepIndex].step_key} onChange={(event) => updateStep(selectedStepIndex, { step_key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} /><span className="field-hint">Lowercase letters, numbers, and underscores.</span></label></div>{form.steps[selectedStepIndex].step_type === "agent" ? <><label>Task instructions<textarea rows={5} maxLength={4000} placeholder="Describe only what this agent should do at this workflow stage." value={form.steps[selectedStepIndex].task_instructions} onChange={(event) => updateStep(selectedStepIndex, { task_instructions: event.target.value })} /></label><div className="workflow-step-grid"><label>Collection access<select value={form.steps[selectedStepIndex].collection_mode} onChange={(event) => updateStep(selectedStepIndex, { collection_mode: event.target.value as CollectionMode })}><option value="off">Off</option><option value="search">Semantic search (prefetched)</option><option value="full_context">Full collection context</option></select></label><label>Maximum output tokens<input type="number" min={256} max={8000} placeholder="Use agent default" value={form.steps[selectedStepIndex].max_output_tokens} onChange={(event) => updateStep(selectedStepIndex, { max_output_tokens: event.target.value })} /></label></div><label>Input artifact keys<input placeholder="candidate_profile, job_fit, interview_answers" value={form.steps[selectedStepIndex].input_artifact_keys} onChange={(event) => updateStep(selectedStepIndex, { input_artifact_keys: event.target.value })} /><span className="field-hint">Optional. Leave blank to use all relevant prior artifacts.</span></label><span className="field-hint">Semantic search is prefetched by the backend, avoiding an extra model tool-planning turn.</span></> : form.steps[selectedStepIndex].step_type === "report" ? <><div className="workflow-step-grid"><label>Input artifact<select required value={form.steps[selectedStepIndex].report_input_key} onChange={(event) => updateStep(selectedStepIndex, { report_input_key: event.target.value })}><option value="">Select prior artifact</option>{form.steps.slice(0, selectedStepIndex).map((step) => <option key={step.step_key} value={step.step_key}>{step.name} ({step.step_key})</option>)}</select></label><label>Template<select value={form.steps[selectedStepIndex].report_template_id} onChange={(event) => updateStep(selectedStepIndex, { report_template_id: event.target.value as "blank_markdown" | "two_column" })}><option value="two_column">Two column</option><option value="blank_markdown">Blank Markdown</option></select></label></div><div className="workflow-step-grid"><label>PDF filename<input required maxLength={120} value={form.steps[selectedStepIndex].report_filename} onChange={(event) => updateStep(selectedStepIndex, { report_filename: event.target.value })} /></label><label>Document title<input maxLength={255} value={form.steps[selectedStepIndex].report_title} onChange={(event) => updateStep(selectedStepIndex, { report_title: event.target.value })} /></label></div><span className="field-hint">This node renders an existing artifact and adds no LLM/API cost.</span></> : null}</section> : null}
        <div className="form-actions"><button type="button" className="btn" onClick={() => { setEditingId(null); setShowWorkflowForm(false); setForm(blank); }}>Cancel</button><button className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save workflow"}</button></div>
      </form>}</section>
    </main> : null}
    {executionMode === "router" ? <main className="box panel">
      <div className="panel-head"><div><h1>Router systems</h1><p>A router selects exactly one normal agent for each request.</p></div><button className="btn btn-primary" type="button" onClick={() => { setEditingRouterId(null); setRouterForm(blankRouter); setSelectedProviderProfile(""); setShowRouterForm(true); setSearchParams({ mode: "router" }); }}>New router</button></div>
      {showRouterForm ? <form className="stack supervisor-create-form multi-agent-edit-form" onSubmit={saveRouter}>
        <div className="panel-accent multi-agent-form-accent"><div className="panel-head"><div><h2>{editingRouterId ? "Edit router" : "New router"}</h2><p>Model, routing instructions, targets, and sharing.</p></div><button type="button" className="icon-close" onClick={() => { setShowRouterForm(false); setEditingRouterId(null); setRouterForm(blankRouter); setSearchParams({ mode: "router" }); }}>×</button></div></div>
        <div className="workflow-step-grid"><label>Name<input required value={routerForm.name} onChange={(event) => setRouterForm({ ...routerForm, name: event.target.value })} /></label><label>Model<select value={routerForm.model} onChange={(event) => setRouterForm({ ...routerForm, model: event.target.value })}>{MODEL_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label} · {option.provider}</option>)}</select></label></div>
        <label>AI provider profile<select value={selectedProviderProfile} onChange={(event) => setSelectedProviderProfile(event.target.value)}><option value="">Inherit my active provider</option>{providerProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.provider === "openai" ? "OpenAI" : "OpenRouter"}</option>)}</select><span className="field-hint">The router and each selected target may use different provider profiles.</span></label>
        <label>Temperature ({routerForm.temperature.toFixed(1)})<input type="range" min={0} max={2} step={0.1} value={routerForm.temperature} onChange={(event) => setRouterForm({ ...routerForm, temperature: Number(event.target.value) })} /></label>
        <label>Routing instructions<textarea rows={6} required value={routerForm.system_prompt} onChange={(event) => setRouterForm({ ...routerForm, system_prompt: event.target.value })} /></label>
        {editingRouterId ? <details className="agent-config-section"><summary><span>Prompt history & evaluation</span><small>Versions, scoring, and AI-assisted drafts</small></summary><div className="agent-config-content"><PromptVersionHistory agentId={editingRouterId} currentPrompt={routerForm.system_prompt} onDraftCreated={(prompt) => setRouterForm((current) => ({ ...current, system_prompt: prompt }))} onRestored={(agent) => { setRouterForm((current) => ({ ...current, system_prompt: agent.system_prompt })); void load(); }} /></div></details> : null}
        {editingRouter ? <details className="agent-config-section"><summary><span>A2A publishing</span><small>Expose this router securely to other platforms</small></summary><div className="agent-config-content"><A2APublishing agent={editingRouter} onChanged={load} /></div></details> : null}
        <details className="agent-config-section"><summary><span>Target agents</span><small>{routerForm.router_target_ids.length + routerForm.router_remote_agent_ids.length} selected</small></summary><div className="agent-config-content"><fieldset className="tool-picker"><legend>Local agents</legend><span className="field-hint">The router selects exactly one local or A2A agent.</span>{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={routerForm.router_target_ids.includes(agent.id)} onChange={(event) => setRouterForm({ ...routerForm, router_target_ids: event.target.checked ? [...routerForm.router_target_ids, agent.id] : routerForm.router_target_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name}</strong><small>{agent.model}</small></span></label>)}</fieldset><fieldset className="tool-picker"><legend>Remote A2A agents</legend>{remoteAgents.map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={routerForm.router_remote_agent_ids.includes(agent.id)} onChange={(event) => setRouterForm({ ...routerForm, router_remote_agent_ids: event.target.checked ? [...routerForm.router_remote_agent_ids, agent.id] : routerForm.router_remote_agent_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name} <em>A2A</em></strong><small>{agent.description || "Remote specialist"}</small></span></label>)}</fieldset></div></details>
        <div className="form-actions"><button className="btn" type="button" onClick={() => { setShowRouterForm(false); setEditingRouterId(null); setRouterForm(blankRouter); setSearchParams({ mode: "router" }); }}>Cancel</button><button className="btn btn-primary" disabled={savingRouter}>{savingRouter ? "Saving..." : editingRouterId ? "Save router" : "Create router"}</button></div>
      </form> : null}
      {loading ? <p>Loading...</p> : !routers.length ? <div className="multi-agent-empty"><p className="idle-title">No routers yet</p><p>Use New router to create one.</p></div> : <ul className="supervisor-system-list">{routers.map((router) => {
        const expanded = expandedRouters.has(router.id);
        const targets = router.router_target_ids.map((id) => agents.find((agent) => agent.id === id)).filter((agent): agent is Agent => Boolean(agent));
        const remoteTargets = router.router_remote_agent_ids.map((id) => remoteAgents.find((agent) => agent.id === id)).filter((agent): agent is RemoteAgent => Boolean(agent));
        return <li key={router.id} className="supervisor-system">
          <button type="button" className="supervisor-system-head" onClick={() => toggleRouter(router.id)} aria-expanded={expanded}>
            <span className={`tree-toggle ${expanded ? "expanded" : ""}`}><span aria-hidden="true" /></span>
            <span className="supervisor-summary"><strong>{router.name}</strong><small>{targets.length + remoteTargets.length} possible targets</small><small>{router.model}</small></span>
            <span className="agent-type-badge supervisor">Router</span>
          </button>
          {expanded ? <div className="supervisor-managed-area"><div className="relationship-graph supervisor-graph"><button type="button" className="relationship-root editable" onClick={() => openRouterEditor(router)}><strong>{router.name}</strong><small>Router · click to edit</small></button>{targets.length + remoteTargets.length ? <><RelationshipArrows count={targets.length + remoteTargets.length} id={`router-${router.id}`} /><div className="relationship-children">{targets.map((agent) => <Link to={`/?edit=${agent.id}`} className="relationship-node" key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small><span>Click to edit</span></Link>)}{remoteTargets.map((agent) => <div className="relationship-node remote" key={`remote-${agent.id}`}><strong>{agent.name}</strong><small>A2A remote agent</small><span>{agent.description || "Remote specialist"}</span></div>)}</div></> : <p>No target agents</p>}</div></div> : null}
        </li>;
      })}</ul>}
    </main> : null}
    {executionMode === "supervisor" ? <main className="box panel">
      <div className="panel-head"><div><h1>Supervisor systems</h1><p>Create supervisors here and open one to see its managed agents.</p></div><button className="btn btn-primary" type="button" onClick={() => { setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setSelectedProviderProfile(""); setShowSupervisorForm(true); setSearchParams({ mode: "supervisor" }); }}>New supervisor</button></div>
      {showSupervisorForm ? <form className="stack supervisor-create-form multi-agent-edit-form" onSubmit={createSupervisor}>
        <div className="panel-accent multi-agent-form-accent"><div className="panel-head"><div><h2>{editingSupervisorId ? "Edit supervisor" : "New supervisor"}</h2><p>Model, instructions, managed agents, and sharing.</p></div><button type="button" className="icon-close" onClick={() => { setShowSupervisorForm(false); setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setSearchParams({ mode: "supervisor" }); }}>×</button></div></div>
        <div className="workflow-step-grid"><label>Name<input required value={supervisorForm.name} onChange={(event) => setSupervisorForm({ ...supervisorForm, name: event.target.value })} /></label><label>Model<select value={supervisorForm.model} onChange={(event) => setSupervisorForm({ ...supervisorForm, model: event.target.value })}>{MODEL_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label} · {option.provider}</option>)}</select></label></div>
        <label>AI provider profile<select value={selectedProviderProfile} onChange={(event) => setSelectedProviderProfile(event.target.value)}><option value="">Inherit my active provider</option>{providerProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.provider === "openai" ? "OpenAI" : "OpenRouter"}</option>)}</select><span className="field-hint">The supervisor and each managed agent may use different provider profiles.</span></label>
        <label>Temperature ({supervisorForm.temperature.toFixed(1)})<input type="range" min={0} max={2} step={0.1} value={supervisorForm.temperature} onChange={(event) => setSupervisorForm({ ...supervisorForm, temperature: Number(event.target.value) })} /></label>
        <label>System prompt<textarea rows={6} required value={supervisorForm.system_prompt} onChange={(event) => setSupervisorForm({ ...supervisorForm, system_prompt: event.target.value })} /></label>
        {editingSupervisorId ? <details className="agent-config-section"><summary><span>Prompt history & evaluation</span><small>Versions, scoring, and AI-assisted drafts</small></summary><div className="agent-config-content"><PromptVersionHistory agentId={editingSupervisorId} currentPrompt={supervisorForm.system_prompt} onDraftCreated={(prompt) => setSupervisorForm((current) => ({ ...current, system_prompt: prompt }))} onRestored={(agent) => {
          setSupervisorForm((current) => ({ ...current, system_prompt: agent.system_prompt }));
          void load();
        }} /></div></details> : null}
        {editingSupervisor ? <details className="agent-config-section"><summary><span>A2A publishing</span><small>Expose this supervisor securely to other platforms</small></summary><div className="agent-config-content"><A2APublishing agent={editingSupervisor} onChanged={load} /></div></details> : null}
        <details className="agent-config-section"><summary><span>Managed agents</span><small>{supervisorForm.managed_agent_ids.length + supervisorForm.managed_remote_agent_ids.length} selected</small></summary><div className="agent-config-content"><fieldset className="tool-picker"><legend>Local agents</legend><span className="field-hint">Local and connected A2A agents can be delegated to.</span>{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={supervisorForm.managed_agent_ids.includes(agent.id)} onChange={(event) => setSupervisorForm({ ...supervisorForm, managed_agent_ids: event.target.checked ? [...supervisorForm.managed_agent_ids, agent.id] : supervisorForm.managed_agent_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name}</strong><small>{agent.model}</small></span></label>)}</fieldset><fieldset className="tool-picker"><legend>Remote A2A agents</legend>{remoteAgents.map((agent) => <label className="tool-option" key={agent.id}><input type="checkbox" checked={supervisorForm.managed_remote_agent_ids.includes(agent.id)} onChange={(event) => setSupervisorForm({ ...supervisorForm, managed_remote_agent_ids: event.target.checked ? [...supervisorForm.managed_remote_agent_ids, agent.id] : supervisorForm.managed_remote_agent_ids.filter((id) => id !== agent.id) })} /><span><strong>{agent.name} <em>A2A</em></strong><small>{agent.description || "Remote specialist"}</small></span></label>)}</fieldset></div></details>
        <div className="form-actions"><button className="btn" type="button" onClick={() => { setShowSupervisorForm(false); setEditingSupervisorId(null); setSupervisorForm(blankSupervisor); setSearchParams({ mode: "supervisor" }); }}>Cancel</button><button className="btn btn-primary" disabled={savingSupervisor}>{savingSupervisor ? "Saving..." : editingSupervisorId ? "Save supervisor" : "Create supervisor"}</button></div>
      </form> : null}
      {loading ? <p>Loading...</p> : !supervisors.length ? <div className="multi-agent-empty"><p className="idle-title">No supervisors yet</p><p>Use New supervisor to create one.</p></div> : <ul className="supervisor-system-list">{supervisors.map((supervisor) => {
        const expanded = expandedSupervisors.has(supervisor.id);
        const managed = supervisor.managed_agent_ids.map((id) => agents.find((agent) => agent.id === id)).filter((agent): agent is Agent => Boolean(agent));
        const managedRemote = supervisor.managed_remote_agent_ids.map((id) => remoteAgents.find((agent) => agent.id === id)).filter((agent): agent is RemoteAgent => Boolean(agent));
        return <li key={supervisor.id} className="supervisor-system">
          <button type="button" className="supervisor-system-head" onClick={() => toggleSupervisor(supervisor.id)} aria-expanded={expanded}>
            <span className={`tree-toggle ${expanded ? "expanded" : ""}`}><span aria-hidden="true" /></span>
            <span className="supervisor-summary"><strong>{supervisor.name}</strong><small>{managed.length + managedRemote.length} managed agents</small><small>{supervisor.model}</small></span>
            <span className="agent-type-badge supervisor">Supervisor</span>
          </button>
          {expanded ? <div className="supervisor-managed-area"><div className="relationship-graph supervisor-graph"><button type="button" className="relationship-root editable" onClick={() => openSupervisorEditor(supervisor)}><strong>{supervisor.name}</strong><small>Supervisor · click to edit</small></button>{managed.length + managedRemote.length ? <><RelationshipArrows count={managed.length + managedRemote.length} id={supervisor.id} twoWay /><div className="relationship-children">{managed.map((agent) => <Link to={`/?edit=${agent.id}`} className="relationship-node" key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small><span>Click to edit</span></Link>)}{managedRemote.map((agent) => <div className="relationship-node remote" key={`remote-${agent.id}`}><strong>{agent.name}</strong><small>A2A remote agent</small><span>{agent.description || "Remote specialist"}</span></div>)}</div></> : <p>No managed agents</p>}</div></div> : null}
        </li>;
      })}</ul>}
    </main> : null}
    {pendingDelete ? <div className="modal-backdrop"><div className="box modal"><h2>Delete workflow?</h2><p><strong>{pendingDelete.name}</strong> and its step definition will be deleted.</p><div className="modal-actions"><button className="btn" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-danger" onClick={() => void remove()}>Delete</button></div></div></div> : null}
  </div>;
}
