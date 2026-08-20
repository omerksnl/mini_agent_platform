export type User = {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
};

export type MeResponse = {
  user: User;
  tenant_name: string;
};

export type Agent = {
  id: string;
  tenant_id: string;
  name: string;
  agent_type: "normal" | "supervisor" | "router";
  supervisor_ids: string[];
  system_prompt: string;
  model: string;
  temperature: number;
  system_tools: string[];
  tool_ids: string[];
  skill_ids: string[];
  collection_ids: string[];
  managed_agent_ids: string[];
  router_target_ids: string[];
  router_ids: string[];
  created_at: string;
  updated_at: string;
};

export type AgentInput = {
  name: string;
  agent_type: "normal" | "supervisor" | "router";
  system_prompt: string;
  model: string;
  temperature: number;
  system_tools: string[];
  tool_ids: string[];
  skill_ids: string[];
  collection_ids: string[];
  managed_agent_ids: string[];
  router_target_ids: string[];
};

export type Skill = {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  instructions: string;
  output_schema: Record<string, unknown> | null;
  required_system_tools: string[];
  required_tool_ids: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SkillInput = Pick<
  Skill,
  "name" | "description" | "instructions" | "output_schema" | "required_system_tools" | "required_tool_ids" | "is_active"
>;

export type ToolParameter = {
  name: string;
  type: "string" | "integer" | "number" | "boolean";
  description: string;
  required: boolean;
};

export type HttpTool = {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  url: string;
  method: "GET" | "POST";
  parameters: ToolParameter[];
  created_at: string;
  updated_at: string;
};

export type HttpToolInput = Pick<
  HttpTool,
  "name" | "description" | "url" | "method" | "parameters"
>;

export type Conversation = {
  id: string;
  tenant_id: string;
  agent_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  used_tools: string[];
  used_skills: string[];
  used_agents: string[];
  api_cost_usd: number;
  attachments: Attachment[];
  created_at: string;
};

export type Attachment = {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type CollectionDocument = { id: string; original_name: string; content_type: string; size_bytes: number; chunk_count: number; created_at: string };
export type Collection = { id: string; tenant_id: string; name: string; description: string; documents: CollectionDocument[]; created_at: string; updated_at: string };

export type WorkflowStepType = "agent" | "http_tool" | "system_tool" | "human_wait" | "report";
export type WorkflowRouteCondition = "success" | "failure" | "input_available" | "always";
export type WorkflowStepInput = {
  step_key: string;
  name: string;
  step_type: WorkflowStepType;
  position: number;
  agent_id: string | null;
  http_tool_id: string | null;
  system_tool_name: string | null;
  config: Record<string, unknown>;
};

export type AgentPromptVersion = {
  id: string;
  agent_id: string;
  version_number: number;
  system_prompt: string;
  created_at: string;
  is_current: boolean;
  evaluation: {
    score?: number;
    overall?: number;
  } | null;
  evaluated_at: string | null;
};
export type WorkflowRouteInput = {
  source_step_key: string;
  target_step_key: string;
  condition: WorkflowRouteCondition;
  priority: number;
  config: Record<string, unknown>;
};
export type WorkflowInput = {
  name: string;
  description: string;
  is_active: boolean;
  steps: WorkflowStepInput[];
  routes: WorkflowRouteInput[];
};
export type WorkflowStep = WorkflowStepInput & { id: string };
export type WorkflowRoute = WorkflowRouteInput & { id: string };
export type Workflow = WorkflowInput & {
  id: string;
  tenant_id: string;
  steps: WorkflowStep[];
  routes: WorkflowRoute[];
  created_at: string;
  updated_at: string;
};
export type WorkflowRunStatus = "running" | "waiting" | "completed" | "failed";
export type WorkflowStepRun = {
  id: string; sequence: number; step_key: string; step_name: string; step_type: WorkflowStepType;
  status: WorkflowRunStatus; input_data: Record<string, unknown>; output_data: Record<string, unknown>;
  error: string | null; api_cost_usd: number; started_at: string; completed_at: string | null;
};
export type WorkflowArtifact = {
  id: string; step_run_id: string | null; sequence: number; artifact_key: string; name: string;
  artifact_type: "workflow_input" | "agent_output" | "human_input" | "tool_output" | "generated_file";
  data: Record<string, unknown>; created_at: string;
};
export type WorkflowRun = {
  id: string; tenant_id: string; workflow_id: string; status: WorkflowRunStatus; current_step_id: string | null;
  input_data: Record<string, unknown>; output_data: Record<string, unknown>; error: string | null;
  total_api_cost_usd: number; step_runs: WorkflowStepRun[]; artifacts: WorkflowArtifact[];
  created_at: string; updated_at: string; completed_at: string | null;
};

const TOKEN_KEY = "access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string"
      ? data.detail
      : response.status === 504
        ? "The agent took too long to respond. Please try again."
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data as T;
}

export const api = {
  async downloadGeneratedFile(path: string, filename: string) {
    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(path, { headers });
    if (!response.ok) throw new Error("Generated PDF could not be downloaded");
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const encodedName = disposition.match(/filename\*=utf-8''([^;]+)/i)?.[1];
    const quotedName = disposition.match(/filename="([^"]+)"/i)?.[1];
    const plainName = disposition.match(/filename=([^;]+)/i)?.[1]?.trim();
    const responseFilename = encodedName
      ? decodeURIComponent(encodedName)
      : quotedName ?? plainName ?? filename;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = responseFilename;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  register(body: {
    email: string;
    password: string;
    full_name: string;
    tenant_name: string;
  }) {
    return request<{ access_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  login(body: { email: string; password: string }) {
    return request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  me() {
    return request<MeResponse>("/api/auth/me");
  },
  listAgents() {
    return request<Agent[]>("/api/agents");
  },
  createAgent(body: AgentInput) {
    return request<Agent>("/api/agents", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  updateAgent(id: string, body: Partial<AgentInput>) {
    return request<Agent>(`/api/agents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  listAgentPromptVersions(id: string) {
    return request<AgentPromptVersion[]>(`/api/agents/${id}/prompt-versions`);
  },
  restoreAgentPromptVersion(id: string, versionId: string) {
    return request<Agent>(`/api/agents/${id}/prompt-versions/${versionId}/restore`, {
      method: "POST",
    });
  },
  evaluateAgentPromptVersions(id: string) {
    return request<{ versions: AgentPromptVersion[]; api_cost_usd: number }>(
      `/api/agents/${id}/prompt-versions/evaluate`,
      { method: "POST" },
    );
  },
  improveAgentPrompt(id: string, draftPrompt: string) {
    return request<{ improved_prompt: string; rationale: string[]; api_cost_usd: number }>(
      `/api/agents/${id}/prompt-improvements`,
      { method: "POST", body: JSON.stringify({ draft_prompt: draftPrompt }) },
    );
  },
  deleteAgent(id: string) {
    return request<void>(`/api/agents/${id}`, { method: "DELETE" });
  },
  listTools() {
    return request<HttpTool[]>("/api/tools");
  },
  createTool(body: HttpToolInput) {
    return request<HttpTool>("/api/tools", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  updateTool(id: string, body: Partial<HttpToolInput>) {
    return request<HttpTool>(`/api/tools/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  deleteTool(id: string) {
    return request<void>(`/api/tools/${id}`, { method: "DELETE" });
  },
  listSkills() {
    return request<Skill[]>("/api/skills");
  },
  createSkill(body: SkillInput) {
    return request<Skill>("/api/skills", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  updateSkill(id: string, body: Partial<SkillInput>) {
    return request<Skill>(`/api/skills/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  deleteSkill(id: string) {
    return request<void>(`/api/skills/${id}`, { method: "DELETE" });
  },
  listCollections() { return request<Collection[]>("/api/collections"); },
  createCollection(body: { name: string; description: string }) {
    return request<Collection>("/api/collections", { method: "POST", body: JSON.stringify(body) });
  },
  deleteCollection(id: string) { return request<void>(`/api/collections/${id}`, { method: "DELETE" }); },
  uploadCollectionDocument(id: string, file: File) {
    const body = new FormData(); body.append("file", file);
    return request<CollectionDocument>(`/api/collections/${id}/documents`, { method: "POST", body });
  },
  deleteCollectionDocument(collectionId: string, id: string) { return request<void>(`/api/collections/${collectionId}/documents/${id}`, { method: "DELETE" }); },
  listWorkflows() { return request<Workflow[]>("/api/workflows"); },
  createWorkflow(body: WorkflowInput) {
    return request<Workflow>("/api/workflows", { method: "POST", body: JSON.stringify(body) });
  },
  updateWorkflow(id: string, body: Partial<WorkflowInput>) {
    return request<Workflow>(`/api/workflows/${id}`, { method: "PATCH", body: JSON.stringify(body) });
  },
  deleteWorkflow(id: string) { return request<void>(`/api/workflows/${id}`, { method: "DELETE" }); },
  listWorkflowRuns(id: string) { return request<WorkflowRun[]>(`/api/workflows/${id}/runs`); },
  startWorkflowRun(id: string, inputData: Record<string, unknown>, attachmentIds: string[] = []) {
    return request<WorkflowRun>(`/api/workflows/${id}/runs`, { method: "POST", body: JSON.stringify({ input_data: inputData, attachment_ids: attachmentIds }) });
  },
  getWorkflowRun(id: string) { return request<WorkflowRun>(`/api/workflows/runs/${id}`); },
  resumeWorkflowRun(id: string, inputData: Record<string, unknown>) {
    return request<WorkflowRun>(`/api/workflows/runs/${id}/resume`, { method: "POST", body: JSON.stringify({ input_data: inputData }) });
  },
  listConversations() {
    return request<Conversation[]>("/api/conversations");
  },
  createConversation(body: { agent_id: string; title: string }) {
    return request<Conversation>("/api/conversations", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  deleteConversation(id: string) {
    return request<void>(`/api/conversations/${id}`, { method: "DELETE" });
  },
  listMessages(conversationId: string) {
    return request<Message[]>(`/api/conversations/${conversationId}/messages`);
  },
  sendMessage(conversationId: string, content: string) {
    return request<Message>(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },
  uploadAttachment(file: File) {
    const body = new FormData();
    body.append("file", file);
    return request<Attachment>("/api/attachments", { method: "POST", body });
  },
  sendMessageWithAttachments(conversationId: string, content: string, attachmentIds: string[]) {
    return request<Message>(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, attachment_ids: attachmentIds }),
    });
  },
  submitHumanFeedback(body: { target_type: "message" | "workflow_run"; target_id: string; score: number; comment: string }) {
    return request<{ status: "submitted" }>("/api/feedback", { method: "POST", body: JSON.stringify(body) });
  },
};
