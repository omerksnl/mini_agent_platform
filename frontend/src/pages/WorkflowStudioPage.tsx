import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppHeader } from "../components/AppHeader";

import {
  api,
  type Agent,
  type RemoteAgent,
  type Workflow,
  type WorkflowInput,
  type WorkflowRouteCondition,
  type WorkflowRouteInput,
  type WorkflowRun,
  type WorkflowArtifact,
  type WorkflowStepInput,
} from "../api";

type Point = { x: number; y: number };
type StudioNode = WorkflowStepInput & { point: Point };
type StudioRoute = WorkflowRouteInput;
type NodeKind = "human_wait" | "report";
type ExecutionStatus = "pending" | "running" | "waiting" | "completed" | "failed";

const CANVAS_WIDTH = 1400;
const CANVAS_HEIGHT = 430;
const NODE_WIDTH = 190;
const NODE_HEIGHT = 92;

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

function ArtifactMarkdown({ data }: { data: Record<string, unknown> }) {
  const humanInput = data.human_input && typeof data.human_input === "object" ? data.human_input as Record<string, unknown> : null;
  const content = typeof data.content === "string" ? data.content : typeof data.result === "string" ? data.result : typeof humanInput?.response === "string" ? humanInput.response : null;
  let markdown = content ?? structuredMarkdown(data);
  if (content) {
    const trimmed = content.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try { markdown = structuredMarkdown(JSON.parse(trimmed)); } catch { /* Keep the model's Markdown. */ }
    }
  }
  return <div className="markdown-content workflow-artifact-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown></div>;
}

function nodeKey(name: string, nodes: StudioNode[]): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "step";
  let result = base;
  let suffix = 2;
  while (nodes.some((node) => node.step_key === result)) result = `${base}_${suffix++}`;
  return result;
}

function defaultPoint(index: number): Point {
  return { x: 80 + (index % 5) * 235, y: 90 + Math.floor(index / 5) * 170 };
}

function stepFromAgent(agent: Agent, nodes: StudioNode[], point: Point): StudioNode {
  const step_key = nodeKey(agent.name, nodes);
  return {
    step_key,
    name: agent.name,
    step_type: "agent",
    position: nodes.length,
    agent_id: agent.id,
    remote_agent_id: null,
    target_workflow_id: null,
    http_tool_id: null,
    system_tool_name: null,
    config: { task_instructions: "", collection_mode: "search", input_artifact_keys: [] },
    point,
  };
}

function stepFromRemoteAgent(agent: RemoteAgent, nodes: StudioNode[], point: Point): StudioNode {
  return {
    step_key: nodeKey(agent.name, nodes), name: agent.name, step_type: "remote_agent",
    position: nodes.length, agent_id: null, remote_agent_id: agent.id,
    target_workflow_id: null,
    http_tool_id: null, system_tool_name: null,
    config: { task_instructions: "", input_artifact_keys: [] }, point,
  };
}

function stepFromKind(kind: NodeKind, nodes: StudioNode[], point: Point): StudioNode {
  const isHuman = kind === "human_wait";
  const name = isHuman ? "Human wait" : "PDF report";
  return {
    step_key: nodeKey(isHuman ? "human_wait" : "pdf_report", nodes),
    name,
    step_type: kind,
    position: nodes.length,
    agent_id: null,
    remote_agent_id: null,
    target_workflow_id: null,
    http_tool_id: null,
    system_tool_name: null,
    config: isHuman
      ? { required_input: "Required human input" }
      : { input_artifact_key: nodes.at(-1)?.step_key ?? "", template_id: "two_column", filename: "{candidate_name}-assessment.pdf", title: "Final Candidate Assessment" },
    point,
  };
}

function stepFromWorkflow(workflow: Workflow, nodes: StudioNode[], point: Point): StudioNode {
  return {
    step_key: nodeKey(workflow.name, nodes), name: workflow.name, step_type: "workflow",
    position: nodes.length, agent_id: null, remote_agent_id: null,
    target_workflow_id: workflow.id, http_tool_id: null, system_tool_name: null,
    config: {}, point,
  };
}

function nodesFromWorkflow(workflow: Workflow): StudioNode[] {
  return [...workflow.steps]
    .sort((a, b) => a.position - b.position)
    .map((step, index) => {
      const stored = step.config.canvas_position;
      const storedPoint = stored && typeof stored === "object" ? stored as Record<string, unknown> : null;
      const point = typeof storedPoint?.x === "number" && typeof storedPoint?.y === "number"
        ? {
            x: Math.max(20, Math.min(CANVAS_WIDTH - NODE_WIDTH - 20, storedPoint.x)),
            y: Math.max(20, Math.min(CANVAS_HEIGHT - NODE_HEIGHT - 20, storedPoint.y)),
          }
        : defaultPoint(index);
      return { ...step, config: { ...step.config }, point };
    });
}

function validateGraph(nodes: StudioNode[], routes: StudioRoute[]): string[] {
  const errors: string[] = [];
  if (nodes.length < 2) return ["Add and connect at least two nodes."];
  const keys = new Set(nodes.map((node) => node.step_key));
  const validRoutes = routes.filter((route) => keys.has(route.source_step_key) && keys.has(route.target_step_key));
  for (const node of nodes) {
    const connected = validRoutes.some((route) => route.source_step_key === node.step_key || route.target_step_key === node.step_key);
    if (!connected) errors.push(`“${node.name}” is not connected to the workflow.`);
  }
  const starts = nodes.filter((node) => !validRoutes.some((route) => route.target_step_key === node.step_key));
  if (starts.length !== 1) errors.push("The workflow must have exactly one start node.");
  if (validRoutes.some((route) => route.source_step_key === route.target_step_key)) errors.push("A node cannot connect to itself.");
  const duplicates = new Set<string>();
  for (const route of validRoutes) {
    const id = `${route.source_step_key}:${route.target_step_key}`;
    if (duplicates.has(id)) errors.push("Duplicate connections are not allowed.");
    duplicates.add(id);
  }
  if (starts.length === 1) {
    const visited = new Set<string>();
    const visiting = new Set<string>();
    let cycle = false;
    const walk = (key: string) => {
      if (visiting.has(key)) { cycle = true; return; }
      if (visited.has(key)) return;
      visiting.add(key);
      validRoutes.filter((route) => route.source_step_key === key).forEach((route) => walk(route.target_step_key));
      visiting.delete(key);
      visited.add(key);
    };
    walk(starts[0].step_key);
    if (cycle) errors.push("Circular connections are not supported yet.");
    const unreachable = nodes.filter((node) => !visited.has(node.step_key));
    if (unreachable.length) errors.push(`Not reachable from the start: ${unreachable.map((node) => node.name).join(", ")}.`);
  }
  return [...new Set(errors)];
}

export function WorkflowStudioPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [remoteAgents, setRemoteAgents] = useState<RemoteAgent[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [active, setActive] = useState(true);
  const [nodes, setNodes] = useState<StudioNode[]>([]);
  const [routes, setRoutes] = useState<StudioRoute[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [connectingFrom, setConnectingFrom] = useState<string | null>(null);
  const [openRouteIndex, setOpenRouteIndex] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingDelete, setPendingDelete] = useState<Workflow | null>(null);
  const [runWorkflow, setRunWorkflow] = useState<Workflow | null>(null);
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);
  const [runInput, setRunInput] = useState("");
  const [humanInput, setHumanInput] = useState("");
  const [runFile, setRunFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [artifactPreview, setArtifactPreview] = useState<WorkflowArtifact | null>(null);
  const pollSequence = useRef(0);

  const selectedNode = nodes.find((node) => node.step_key === selectedKey) ?? null;
  const graphErrors = useMemo(() => nodes.length ? validateGraph(nodes, routes) : [], [nodes, routes]);

  async function load() {
    setLoading(true);
    try {
      const [workflowItems, agentItems, remoteItems] = await Promise.all([api.listWorkflows(), api.listAgents(), api.listRemoteAgents()]);
      setWorkflows(workflowItems);
      setAgents(agentItems);
      setRemoteAgents(remoteItems);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workflow data could not be loaded");
    } finally { setLoading(false); }
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
      } catch { /* Retry on the next interval. */ }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 750);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeRun?.id, activeRun?.status]);

  function resetEditor() {
    setEditingId(null); setName(""); setDescription(""); setActive(true); setNodes([]); setRoutes([]);
    setSelectedKey(null); setConnectingFrom(null); setOpenRouteIndex(null); setError("");
  }

  function openWorkflow(workflow: Workflow) {
    setEditingId(workflow.id); setName(workflow.name); setDescription(workflow.description); setActive(workflow.is_active);
    setNodes(nodesFromWorkflow(workflow));
    setRoutes(workflow.routes.map((route) => ({ ...route, config: { ...route.config } })));
    setSelectedKey(null); setConnectingFrom(null); setOpenRouteIndex(null); setError("");
  }

  function addNode(token: string, point: Point) {
    if (token === "human_wait" || token === "report") {
      setNodes((current) => [...current, stepFromKind(token, current, point)]);
      return;
    }
    const agent = agents.find((item) => item.id === token && item.agent_type === "normal");
    if (agent) setNodes((current) => [...current, stepFromAgent(agent, current, point)]);
    const remote = remoteAgents.find((item) => `remote:${item.id}` === token);
    if (remote) setNodes((current) => [...current, stepFromRemoteAgent(remote, current, point)]);
    const nested = workflows.find((item) => `workflow:${item.id}` === token && item.id !== editingId);
    if (nested) setNodes((current) => [...current, stepFromWorkflow(nested, current, point)]);
  }

  function dropOnCanvas(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const point = {
      x: Math.max(20, Math.min(CANVAS_WIDTH - NODE_WIDTH - 20, event.clientX - bounds.left + event.currentTarget.scrollLeft - NODE_WIDTH / 2)),
      y: Math.max(20, Math.min(CANVAS_HEIGHT - NODE_HEIGHT - 20, event.clientY - bounds.top + event.currentTarget.scrollTop - NODE_HEIGHT / 2)),
    };
    const movingKey = event.dataTransfer.getData("application/x-workflow-move");
    if (movingKey) {
      setNodes((current) => current.map((node) => node.step_key === movingKey ? { ...node, point } : node));
      return;
    }
    const token = event.dataTransfer.getData("application/x-workflow-node");
    if (token) addNode(token, point);
  }

  function connectTo(targetKey: string) {
    if (!connectingFrom || connectingFrom === targetKey) { setConnectingFrom(null); return; }
    const exists = routes.some((route) => route.source_step_key === connectingFrom && route.target_step_key === targetKey);
    if (!exists) setRoutes((current) => [...current, { source_step_key: connectingFrom, target_step_key: targetKey, condition: "success", priority: 0, config: {} }]);
    setConnectingFrom(null);
  }

  function removeNode(key: string) {
    setNodes((current) => current.filter((node) => node.step_key !== key));
    setRoutes((current) => current.filter((route) => route.source_step_key !== key && route.target_step_key !== key));
    if (selectedKey === key) setSelectedKey(null);
    if (connectingFrom === key) setConnectingFrom(null);
  }

  function patchNode(key: string, patch: Partial<StudioNode>) {
    setNodes((current) => current.map((node) => node.step_key === key ? { ...node, ...patch } : node));
  }

  function patchConfig(key: string, patch: Record<string, unknown>) {
    setNodes((current) => current.map((node) => node.step_key === key ? { ...node, config: { ...node.config, ...patch } } : node));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const issues = validateGraph(nodes, routes);
    if (issues.length) { setError(issues[0]); return; }
    setSaving(true); setError("");
    const orderedNodes = [...nodes].sort((a, b) => a.point.x - b.point.x || a.point.y - b.point.y);
    const body: WorkflowInput = {
      name: name.trim(), description: description.trim(), is_active: active,
      steps: orderedNodes.map(({ point, ...node }, position) => ({ ...node, position, config: { ...node.config, canvas_position: point } })),
      routes,
    };
    try {
      if (editingId) await api.updateWorkflow(editingId, body); else await api.createWorkflow(body);
      resetEditor(); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Workflow could not be saved"); }
    finally { setSaving(false); }
  }

  async function deleteWorkflow() {
    if (!pendingDelete) return;
    try {
      await api.deleteWorkflow(pendingDelete.id);
      if (editingId === pendingDelete.id) resetEditor();
      setPendingDelete(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workflow could not be deleted");
    }
  }

  function openRunner(workflow: Workflow) {
    openWorkflow(workflow);
    setRunWorkflow(workflow); setActiveRun(null); setRunInput(""); setHumanInput(""); setRunFile(null); setArtifactPreview(null); setError("");
  }

  async function startRun(event: FormEvent) {
    event.preventDefault();
    if (!runWorkflow) return;
    setRunning(true); setError("");
    try {
      const attachment = runFile ? await api.uploadAttachment(runFile) : null;
      setActiveRun(await api.startWorkflowRun(runWorkflow.id, { request: runInput.trim() }, attachment ? [attachment.id] : []));
      setRunFile(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Workflow could not be started"); }
    finally { setRunning(false); }
  }

  async function continueRun() {
    if (!activeRun) return;
    setRunning(true); setError("");
    try { setActiveRun(await api.resumeWorkflowRun(activeRun.id, { response: humanInput.trim() })); setHumanInput(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Workflow could not be resumed"); }
    finally { setRunning(false); }
  }

  async function resumeRun(event: FormEvent) {
    event.preventDefault();
    await continueRun();
  }

  const completedSteps = activeRun?.step_runs.filter((step) => step.status === "completed").length ?? 0;
  const runProgress = runWorkflow ? Math.round((completedSteps / runWorkflow.steps.length) * 100) : 0;
  const waitingDefinition = activeRun?.current_step_id ? runWorkflow?.steps.find((step) => "id" in step && step.id === activeRun.current_step_id) : null;
  const waitingStepRun = activeRun?.step_runs.find((step) => step.status === "waiting");
  const nestedRequiredInput = typeof waitingStepRun?.output_data.required_input === "string"
    ? waitingStepRun.output_data.required_input
    : "";
  const requiredHumanInput = nestedRequiredInput.trim()
    || (typeof waitingDefinition?.config.required_input === "string" && waitingDefinition.config.required_input.trim()
      ? waitingDefinition.config.required_input
      : "Required human input");
  const executionMode = Boolean(activeRun && runWorkflow);
  const stepRunFor = (key: string) => activeRun?.step_runs.find((step) => step.step_key === key);
  const statusFor = (key: string): ExecutionStatus => (stepRunFor(key)?.status as ExecutionStatus | undefined) ?? "pending";
  const artifactFor = (key: string) => {
    const stepRun = stepRunFor(key);
    return stepRun ? [...(activeRun?.artifacts ?? [])].reverse().find((artifact) => artifact.step_run_id === stepRun.id) : undefined;
  };
  const routeWasTaken = (sourceKey: string, routeIndex: number) => {
    const source = nodes.find((node) => node.step_key === sourceKey);
    const stepRun = stepRunFor(sourceKey);
    if (!source || !stepRun || (stepRun.status !== "completed" && stepRun.status !== "failed")) return false;
    const event: WorkflowRouteCondition = stepRun.status === "failed" ? "failure" : source.step_type === "human_wait" ? "input_available" : "success";
    const outgoing = routes.map((route, index) => ({ route, index })).filter(({ route }) => route.source_step_key === sourceKey).sort((a, b) => a.route.priority - b.route.priority);
    const exact = outgoing.filter(({ route }) => route.condition === event);
    const selected = exact.length ? exact : outgoing.filter(({ route }) => route.condition === "always");
    return selected.some(({ index }) => index === routeIndex);
  };

  return <div className="app-shell workflow-studio-page">
    <AppHeader />
    {error ? <p className="error">{error}</p> : null}
    <main className="workflow-studio-shell">
      <aside className="box workflow-studio-library">
        <div className="panel-head"><div><h1>Workflows</h1><p>Existing workflows use the same backend definitions.</p></div><button className="btn btn-primary" type="button" onClick={resetEditor}>New</button></div>
        {loading ? <p>Loading...</p> : workflows.length ? <ul>{workflows.map((workflow) => <li className="studio-workflow-item" key={workflow.id}><button className={editingId === workflow.id ? "selected" : ""} type="button" onClick={() => openWorkflow(workflow)}><strong>{workflow.name}</strong><small>{workflow.steps.length} nodes · {workflow.routes.length} connections</small></button><span className="studio-workflow-actions"><button className="studio-workflow-run" type="button" disabled={!workflow.is_active} aria-label={`Run ${workflow.name}`} title="Run workflow" onClick={() => openRunner(workflow)}>▶</button><button className="studio-workflow-delete" type="button" aria-label={`Delete ${workflow.name}`} title="Delete workflow" onClick={() => setPendingDelete(workflow)}>×</button></span></li>)}</ul> : <p>No workflows yet.</p>}
        <hr />
        <h2>Node list</h2><p className="field-hint">Drag a node onto the canvas.</p>
        <div className="studio-palette-list">
          <details className="studio-palette-group" open>
            <summary><span>Agents</span><small>{agents.filter((agent) => agent.agent_type === "normal").length}</small></summary>
            <div className="studio-palette-content">{agents.filter((agent) => agent.agent_type === "normal").map((agent) => <div className="palette-node" draggable onDragStart={(event) => event.dataTransfer.setData("application/x-workflow-node", agent.id)} key={agent.id}><strong>{agent.name}</strong><small>{agent.model}</small></div>)}</div>
          </details>
          <details className="studio-palette-group">
            <summary><span>Remote agents</span><small>{remoteAgents.length}</small></summary>
            <div className="studio-palette-content">{remoteAgents.length ? remoteAgents.map((agent) => <div className="palette-node remote" draggable onDragStart={(event) => event.dataTransfer.setData("application/x-workflow-node", `remote:${agent.id}`)} key={`remote-${agent.id}`}><strong>{agent.name} · A2A</strong><small>{agent.description || "Remote specialist"}</small></div>) : <small className="palette-empty">No remote agents</small>}</div>
          </details>
          <details className="studio-palette-group">
            <summary><span>Workflows</span><small>{workflows.filter((workflow) => workflow.id !== editingId && workflow.is_active).length}</small></summary>
            <div className="studio-palette-content">{workflows.filter((workflow) => workflow.id !== editingId && workflow.is_active).map((workflow) => <div className="palette-node workflow" draggable onDragStart={(event) => event.dataTransfer.setData("application/x-workflow-node", `workflow:${workflow.id}`)} key={`workflow-${workflow.id}`}><strong>{workflow.name}</strong><small>Returns final output only</small></div>)}</div>
          </details>
          <details className="studio-palette-group">
            <summary><span>Special nodes</span><small>2</small></summary>
            <div className="studio-palette-content"><div className="palette-node human" draggable onDragStart={(event) => event.dataTransfer.setData("application/x-workflow-node", "human_wait")}><strong>Human wait</strong><small>Pause for user input</small></div><div className="palette-node report" draggable onDragStart={(event) => event.dataTransfer.setData("application/x-workflow-node", "report")}><strong>PDF report</strong><small>Render an artifact</small></div></div>
          </details>
        </div>
        <div className="studio-delete-drop" onDragOver={(event) => { if (event.dataTransfer.types.includes("application/x-workflow-move")) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }} onDrop={(event) => { event.preventDefault(); const key = event.dataTransfer.getData("application/x-workflow-move"); if (key) removeNode(key); }}>
          <span aria-hidden="true">×</span><strong>Remove from workflow</strong><small>Drop a canvas node here</small>
        </div>
      </aside>
      <form className="box workflow-studio-main" onSubmit={save}>
        <div className="workflow-studio-meta"><label>Name<input required value={name} onChange={(event) => setName(event.target.value)} placeholder="New workflow" /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What does this workflow do?" /></label><label className="checkbox-line"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />Active</label></div>
        {executionMode && activeRun ? <div className={`studio-execution-bar status-${activeRun.status}`}><span><strong>{activeRun.status === "waiting" ? "Waiting for human input" : activeRun.status}</strong><small>{completedSteps}/{runWorkflow?.steps.length ?? nodes.length} nodes · ${activeRun.total_api_cost_usd.toFixed(6)}</small></span><div className="workflow-progress"><span style={{ width: `${runProgress}%` }} /></div><button type="button" className="icon-close" title="Close execution view" onClick={() => { setRunWorkflow(null); setActiveRun(null); setArtifactPreview(null); }}>×</button></div> : null}
        <div className="workflow-studio-canvas" onDragOver={(event) => event.preventDefault()} onDrop={dropOnCanvas}>
          <div className="workflow-studio-board" style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}>
            {!nodes.length ? <div className="studio-empty"><strong>Drag the first node here</strong><span>Then connect its output to the next node’s input.</span></div> : null}
            <svg className="studio-edges" width={CANVAS_WIDTH} height={CANVAS_HEIGHT} aria-hidden="true"><defs>{(["pending", "running", "waiting", "completed", "failed"] as ExecutionStatus[]).map((status) => <marker id={`workflow-arrow-${status}`} className={`marker-${status}`} key={status} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker>)}</defs>{routes.map((route, index) => { const source = nodes.find((node) => node.step_key === route.source_step_key); const target = nodes.find((node) => node.step_key === route.target_step_key); if (!source || !target) return null; const x1 = source.point.x + NODE_WIDTH; const y1 = source.point.y + NODE_HEIGHT / 2; const x2 = target.point.x; const y2 = target.point.y + NODE_HEIGHT / 2; const curve = Math.max(70, Math.abs(x2 - x1) * 0.45); const sourceStatus = executionMode ? statusFor(source.step_key) : "pending"; const chosen = executionMode && routeWasTaken(source.step_key, index); return <path className={`studio-edge-path status-${sourceStatus}${chosen ? " taken" : ""}`} key={`${route.source_step_key}-${route.target_step_key}-${index}`} d={`M ${x1} ${y1} C ${x1 + curve} ${y1}, ${x2 - curve} ${y2}, ${x2} ${y2}`} markerEnd={`url(#workflow-arrow-${sourceStatus})`} />; })}</svg>
            {routes.map((route, index) => {
              const source = nodes.find((node) => node.step_key === route.source_step_key);
              const target = nodes.find((node) => node.step_key === route.target_step_key);
              if (!source || !target) return null;
              const left = (source.point.x + NODE_WIDTH + target.point.x) / 2;
              const top = (source.point.y + target.point.y) / 2 + NODE_HEIGHT / 2;
              return <div className={`studio-edge-control${openRouteIndex === index ? " open" : ""}`} style={{ left, top }} key={`control-${route.source_step_key}-${route.target_step_key}-${index}`}>
                <button type="button" className="studio-edge-trigger" aria-label={`Edit ${source.name} to ${target.name} connection`} aria-expanded={openRouteIndex === index} onClick={() => setOpenRouteIndex((current) => current === index ? null : index)}><span /></button>
                {openRouteIndex === index ? <div className="studio-edge-menu">
                  <strong>Route condition</strong>
                  {(["success", "failure", "input_available", "always"] as WorkflowRouteCondition[]).map((condition) => <button type="button" className={route.condition === condition ? "selected" : ""} key={condition} onClick={() => { setRoutes((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, condition } : item)); setOpenRouteIndex(null); }}>{condition.replace("_", " ")}</button>)}
                  <button type="button" className="delete" onClick={() => { setRoutes((current) => current.filter((_, itemIndex) => itemIndex !== index)); setOpenRouteIndex(null); }}>Delete connection</button>
                </div> : null}
              </div>;
            })}
            {nodes.map((node) => { const nodeStatus = statusFor(node.step_key); const artifact = artifactFor(node.step_key); const generatedFile = artifact?.artifact_type === "generated_file" ? artifact.data as Record<string, unknown> : null; const isWaiting = executionMode && nodeStatus === "waiting"; return <article className={`studio-node ${node.step_type}${executionMode ? ` execution-${nodeStatus}` : ""}${selectedKey === node.step_key ? " selected" : ""}${connectingFrom && connectingFrom !== node.step_key ? " connection-target" : ""}${graphErrors.some((message) => message.includes(`“${node.name}”`)) ? " invalid" : ""}`} draggable={!executionMode && !connectingFrom} onDragStart={(event) => { if (executionMode) return; event.dataTransfer.setData("application/x-workflow-move", node.step_key); event.dataTransfer.effectAllowed = "move"; }} style={{ left: node.point.x, top: node.point.y }} key={node.step_key} onClick={() => { if (executionMode) { if (artifact) setArtifactPreview(artifact); return; } if (connectingFrom && connectingFrom !== node.step_key) connectTo(node.step_key); else setSelectedKey(node.step_key); }}>
              <button draggable={false} type="button" className={`node-port input${connectingFrom && connectingFrom !== node.step_key ? " ready" : ""}`} aria-label={`Connect to ${node.name}`} onMouseDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); connectTo(node.step_key); }} />
              <strong>{node.name}</strong><small>{executionMode ? nodeStatus : node.step_type.replace("_", " ")}</small>
              {artifact ? <button type="button" className="node-artifact-action" onClick={(event) => { event.stopPropagation(); setArtifactPreview(artifact); }}>View artifact</button> : null}
              {generatedFile && typeof generatedFile.download_url === "string" ? <button type="button" className="node-download-action" onClick={(event) => { event.stopPropagation(); void api.downloadGeneratedFile(generatedFile.download_url as string, typeof generatedFile.filename === "string" ? generatedFile.filename : "report.pdf"); }}>Download PDF</button> : null}
              {isWaiting ? <div className="node-human-input" onClick={(event) => event.stopPropagation()}><label>{requiredHumanInput}<textarea rows={3} value={humanInput} onChange={(event) => setHumanInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && humanInput.trim() && !running) { event.preventDefault(); void continueRun(); } }} /></label><button type="button" className="btn btn-primary btn-compact" disabled={running || !humanInput.trim()} onClick={() => void continueRun()}>{running ? "Continuing..." : "Continue"}</button></div> : null}
              <button draggable={false} type="button" className={`node-port output${connectingFrom === node.step_key ? " active" : ""}`} aria-label={`Connect from ${node.name}`} title="Start another connection" onMouseDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); setConnectingFrom((current) => current === node.step_key ? null : node.step_key); }}><span aria-hidden="true">+</span></button>
            </article>; })}
          </div>
        </div>
        {selectedNode ? <section className="studio-node-settings">
          <div className="panel-head"><div><h2>Node settings</h2><p>{selectedNode.step_key}</p></div><button type="button" className="btn btn-danger btn-compact" onClick={() => removeNode(selectedNode.step_key)}>Remove node</button></div>
          <label>Artifact name<input value={selectedNode.name} onChange={(event) => patchNode(selectedNode.step_key, { name: event.target.value })} /></label>
          {selectedNode.step_type === "agent" || selectedNode.step_type === "remote_agent" ? <label>Task instructions<textarea rows={4} value={String(selectedNode.config.task_instructions ?? "")} onChange={(event) => patchConfig(selectedNode.step_key, { task_instructions: event.target.value })} /></label> : null}
          {selectedNode.step_type === "workflow" ? <p className="field-hint">This node runs the selected workflow and exposes only its final output. Internal artifacts stay inside the child run.</p> : null}
          {selectedNode.step_type === "human_wait" ? <label>Required input<textarea rows={3} value={String(selectedNode.config.required_input ?? "")} onChange={(event) => patchConfig(selectedNode.step_key, { required_input: event.target.value })} /></label> : null}
          {selectedNode.step_type === "report" ? <div className="workflow-step-grid"><label>Input artifact key<input value={String(selectedNode.config.input_artifact_key ?? "")} onChange={(event) => patchConfig(selectedNode.step_key, { input_artifact_key: event.target.value })} /></label><label>Template<select value={String(selectedNode.config.template_id ?? "two_column")} onChange={(event) => patchConfig(selectedNode.step_key, { template_id: event.target.value })}><option value="two_column">Two column</option><option value="blank_markdown">Blank Markdown</option></select></label></div> : null}
          {routes.filter((route) => route.target_step_key === selectedNode.step_key).length > 1 ? <label>Join behavior<select value={String(selectedNode.config.join_mode ?? "all")} onChange={(event) => patchConfig(selectedNode.step_key, { join_mode: event.target.value })}><option value="all">Wait for all incoming branches</option><option value="any">Continue with first available branch</option></select></label> : null}
          <div className="studio-route-settings">{routes.filter((route) => route.source_step_key === selectedNode.step_key).map((route, index) => <div key={`${route.target_step_key}-${index}`}><span>→ {nodes.find((node) => node.step_key === route.target_step_key)?.name}</span><select value={route.condition} onChange={(event) => setRoutes((current) => current.map((item) => item === route ? { ...item, condition: event.target.value as WorkflowRouteCondition } : item))}><option value="success">success</option><option value="failure">failure</option><option value="input_available">input available</option><option value="always">always</option></select><button type="button" aria-label="Remove connection" onClick={() => setRoutes((current) => current.filter((item) => item !== route))}>×</button></div>)}</div>
        </section> : null}
        <div className="workflow-studio-footer"><span>{connectingFrom ? "Select the input port of the next node." : graphErrors[0] ?? `${nodes.length} nodes · ${routes.length} connections`}</span><div><button className="btn btn-primary" disabled={saving || Boolean(graphErrors.length)}>{saving ? "Saving..." : "Save workflow"}</button></div></div>
      </form>
    </main>
    {runWorkflow ? <div className="modal-backdrop"><div className="box modal workflow-studio-runner"><div className="panel-head"><div><h2>{runWorkflow.name}</h2><p>Run and monitor this workflow.</p></div><button className="icon-close" type="button" onClick={() => { setRunWorkflow(null); setActiveRun(null); }}>×</button></div>{!activeRun ? <form className="stack" onSubmit={startRun}><label>Initial request<textarea rows={5} required value={runInput} onChange={(event) => setRunInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !running) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="Describe the task and provide the initial workflow input." /></label><div className="workflow-run-attachment"><label className="btn attachment-button">Attach PDF<input type="file" accept="application/pdf,.pdf" disabled={running} onChange={(event) => setRunFile(event.target.files?.[0] ?? null)} /></label>{runFile ? <span className="pending-attachment">{runFile.name}<button type="button" onClick={() => setRunFile(null)}>×</button></span> : null}</div><button className="btn btn-primary" disabled={running}>{running ? "Starting..." : "Start workflow"}</button></form> : <div className="stack"><div className={`workflow-run-summary status-${activeRun.status}`}><span><strong>{activeRun.status === "waiting" ? "Waiting for human input" : activeRun.status}</strong><small>{completedSteps} of {runWorkflow.steps.length} steps completed</small></span><strong>{runProgress}%</strong></div><div className="workflow-progress"><span style={{ width: `${runProgress}%` }} /></div><ol className="workflow-run-steps">{[...runWorkflow.steps].sort((a, b) => a.position - b.position).map((definition) => { const stepRun = activeRun.step_runs.find((step) => step.step_key === definition.step_key); const status = stepRun?.status ?? "pending"; return <li className={`run-step status-${status}`} key={definition.id}><span className="run-step-marker" /><span><strong>{definition.name}</strong><small>{definition.step_type.replace("_", " ")} · {status}</small>{stepRun?.error ? <small className="run-step-error">{stepRun.error}</small> : null}</span>{stepRun?.api_cost_usd ? <small>${stepRun.api_cost_usd.toFixed(6)}</small> : null}</li>; })}</ol>{activeRun.artifacts.length ? <section className="studio-run-artifacts"><h3>Artifacts</h3>{activeRun.artifacts.map((artifact) => <details key={artifact.id}><summary>{artifact.name}</summary><pre>{JSON.stringify(artifact.data, null, 2)}</pre></details>)}</section> : null}{activeRun.status === "waiting" ? <form className="human-wait-form" onSubmit={resumeRun}><label>{requiredHumanInput}<textarea rows={4} required value={humanInput} onChange={(event) => setHumanInput(event.target.value)} /></label><button className="btn btn-primary" disabled={running}>{running ? "Continuing..." : "Continue workflow"}</button></form> : null}{activeRun.status === "failed" ? <p className="error">{activeRun.error}</p> : null}{activeRun.status === "completed" ? <details className="workflow-result"><summary><strong>Final output</strong><span>View</span></summary><pre>{JSON.stringify(activeRun.output_data.last_output ?? activeRun.output_data, null, 2)}</pre></details> : null}<p className="workflow-run-cost">API cost: ${activeRun.total_api_cost_usd.toFixed(6)}</p></div>}</div></div> : null}
    {pendingDelete ? <div className="modal-backdrop"><div className="box modal"><h2>Delete workflow?</h2><p><strong>{pendingDelete.name}</strong> and all its node connections will be deleted. The agents themselves will remain available.</p><div className="modal-actions"><button className="btn" type="button" onClick={() => setPendingDelete(null)}>Cancel</button><button className="btn btn-danger" type="button" onClick={() => void deleteWorkflow()}>Delete</button></div></div></div> : null}
    {artifactPreview ? <div className="modal-backdrop studio-artifact-preview"><div className="box modal"><div className="panel-head"><div><h2>{artifactPreview.name}</h2><p>{artifactPreview.artifact_type.replace("_", " ")}</p></div><button type="button" className="icon-close" onClick={() => setArtifactPreview(null)}>×</button></div><div className="studio-artifact-scroll"><ArtifactMarkdown data={artifactPreview.data} /></div></div></div> : null}
  </div>;
}
