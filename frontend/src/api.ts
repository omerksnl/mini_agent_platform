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
  collection_search_limit: number;
  a2a_enabled: boolean;
  a2a_description: string;
  system_tools: string[];
  tool_ids: string[];
  skill_ids: string[];
  collection_ids: string[];
  guardrail_ids: string[];
  managed_agent_ids: string[];
  router_target_ids: string[];
  managed_remote_agent_ids: string[];
  router_remote_agent_ids: string[];
  remote_agent_ids: string[];
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
  collection_search_limit: number;
  system_tools: string[];
  tool_ids: string[];
  skill_ids: string[];
  collection_ids: string[];
  guardrail_ids: string[];
  managed_agent_ids: string[];
  router_target_ids: string[];
  managed_remote_agent_ids: string[];
  router_remote_agent_ids: string[];
  remote_agent_ids: string[];
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

export type Guardrail = {
  id: string; tenant_id: string; name: string;
  guardrail_type: "pii_redaction" | "blocked_terms" | "required_output_fields";
  stages: Array<"input" | "tool_input" | "tool_output" | "output">;
  action: "warn" | "redact" | "block";
  config: Record<string, unknown>; is_active: boolean; created_at: string; updated_at: string;
};

export type ProfileUpdate = {
  full_name?: string;
  email?: string;
  tenant_name?: string;
  current_password?: string;
  new_password?: string;
};
export type GuardrailInput = Pick<Guardrail, "name" | "guardrail_type" | "stages" | "action" | "config" | "is_active">;

export type VisualModel = {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  task_type: "image_classification";
  architecture: "simple_cnn" | "mobilenet_v2" | "resnet50";
  class_names: string[];
  image_width: number;
  image_height: number;
  channels: 1 | 3;
  use_pretrained_weights: boolean;
  status: "draft" | "dataset_ready" | "training" | "trained" | "training_failed";
  created_at: string;
  updated_at: string;
};

export type VisualModelInput = Pick<
  VisualModel,
  "name" | "description" | "task_type" | "architecture" | "class_names" |
  "image_width" | "image_height" | "channels" | "use_pretrained_weights"
>;

export type VisualDatasetSummary = {
  visual_model_id: string;
  total_images: number;
  total_bytes: number;
  ready_for_training: boolean;
  classes: Array<{ class_name: string; image_count: number; total_bytes: number }>;
};

export type VisualDatasetUploadResult = {
  added_images: number;
  skipped_duplicates: number;
  summary: VisualDatasetSummary;
};

export type VisualTrainingRun = {
  id: string;
  tenant_id: string;
  visual_model_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  epochs: number;
  batch_size: number;
  validation_split: number;
  learning_rate: number;
  requested_device: "auto" | "cpu" | "gpu";
  used_device: "cpu" | "gpu" | null;
  device_name: string | null;
  current_epoch: number;
  metrics: Record<string, number>;
  training_history: Record<string, number[]>;
  evaluation: VisualModelEvaluation | Record<string, never>;
  artifact_path: string | null;
  version_number: number | null;
  is_active: boolean;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type VisualModelEvaluation = {
  sample_count: number;
  evaluated_at: string;
  summary: {
    accuracy: number;
    balanced_accuracy: number;
    macro_precision: number;
    macro_recall: number;
    macro_f1: number;
    weighted_precision: number;
    weighted_recall: number;
    weighted_f1: number;
  };
  classes: Array<{
    class_name: string;
    precision: number;
    recall: number;
    f1: number;
    support: number;
  }>;
  confusion_matrix: number[][];
  confidence_histogram: { labels: string[]; counts: number[] };
};

export type VisualComputeDevice = {
  value: "cpu" | "gpu";
  label: string;
  available: boolean;
  description: string;
};

export type VisualTrainingInput = Pick<VisualTrainingRun, "epochs" | "batch_size" | "validation_split" | "learning_rate" | "requested_device">;

export type VisualPrediction = {
  predicted_class: string;
  confidence: number;
  scores: Array<{ class_name: string; probability: number }>;
  training_run_id: string;
};

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

export type WorkflowStepType = "agent" | "remote_agent" | "workflow" | "http_tool" | "system_tool" | "human_wait" | "report";
export type WorkflowRouteCondition = "success" | "failure" | "input_available" | "always";
export type WorkflowStepInput = {
  step_key: string;
  name: string;
  step_type: WorkflowStepType;
  position: number;
  agent_id: string | null;
  remote_agent_id: string | null;
  target_workflow_id: string | null;
  http_tool_id: string | null;
  system_tool_name: string | null;
  config: Record<string, unknown>;
};

export type ProviderSettings = {
  provider: "openrouter" | "openai";
  source: "personal" | "platform";
  has_personal_key: boolean;
  masked_key: string | null;
};
export type ProviderCredential = {
  id: string; name: string; provider: "openrouter" | "openai";
  masked_key: string; is_active: boolean; created_at: string;
};
export type AgentProviderAssignment = { agent_id: string; credential_id: string };
export type ProviderCompatibility = {
  provider: "openrouter" | "openai";
  incompatible_agents: string[];
  recommended_model: string | null;
};

export type A2APublishResponse = {
  api_key: string;
  agent_card_url: string;
  endpoint_url: string;
};

export type RemoteAgent = {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  agent_card_url: string;
  endpoint_url: string;
  protocol_version: string;
  billing_mode: "owner" | "caller";
  provider_credential_id: string | null;
  skills: Array<{ id?: string; name?: string; description?: string; tags?: string[] }>;
  created_at: string;
  updated_at: string;
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
  updateProfile(body: ProfileUpdate) {
    return request<MeResponse>("/api/auth/profile", { method: "PATCH", body: JSON.stringify(body) });
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
  getProviderSettings() {
    return request<ProviderSettings>("/api/provider-settings");
  },
  updateProviderSettings(name: string, provider: "openrouter" | "openai", apiKey: string) {
    return request<ProviderSettings>("/api/provider-settings", {
      method: "PUT", body: JSON.stringify({ name, provider, api_key: apiKey }),
    });
  },
  clearProviderSettings() {
    return request<void>("/api/provider-settings", { method: "DELETE" });
  },
  testProviderSettings() {
    return request<{ status: "ok"; provider: "openrouter" | "openai" }>("/api/provider-settings/test", { method: "POST" });
  },
  listProviderModels() {
    return request<Array<{ id: string; label: string }>>("/api/provider-settings/models");
  },
  listProviderCredentials() {
    return request<ProviderCredential[]>("/api/provider-settings/credentials");
  },
  listAgentProviderAssignments() {
    return request<AgentProviderAssignment[]>("/api/provider-settings/agent-assignments");
  },
  setAgentProviderAssignment(agentId: string, credentialId: string | null) {
    return request<void>(`/api/provider-settings/agent-assignments/${agentId}`, {
      method: "PUT", body: JSON.stringify({ credential_id: credentialId }),
    });
  },
  activateProviderCredential(id: string) {
    return request<ProviderSettings>(`/api/provider-settings/credentials/${id}/activate`, { method: "POST" });
  },
  deleteProviderCredential(id: string) {
    return request<void>(`/api/provider-settings/credentials/${id}`, { method: "DELETE" });
  },
  getProviderCompatibility() {
    return request<ProviderCompatibility>("/api/provider-settings/compatibility");
  },
  migrateProviderModels() {
    return request<ProviderCompatibility>("/api/provider-settings/compatibility/migrate", { method: "POST" });
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
  publishAgentA2A(id: string, description: string) {
    return request<A2APublishResponse>(`/api/agents/${id}/a2a/publish`, {
      method: "POST",
      body: JSON.stringify({ description }),
    });
  },
  unpublishAgentA2A(id: string) {
    return request<Agent>(`/api/agents/${id}/a2a/publish`, { method: "DELETE" });
  },
  listRemoteAgents() {
    return request<RemoteAgent[]>("/api/remote-agents");
  },
  createRemoteAgent(agentCardUrl: string, apiKey: string, billingMode: "owner" | "caller", providerCredentialId: string | null) {
    return request<RemoteAgent>("/api/remote-agents", {
      method: "POST",
      body: JSON.stringify({ agent_card_url: agentCardUrl, api_key: apiKey, billing_mode: billingMode, provider_credential_id: providerCredentialId }),
    });
  },
  deleteRemoteAgent(id: string) {
    return request<void>(`/api/remote-agents/${id}`, { method: "DELETE" });
  },
  sendRemoteAgentMessage(id: string, content: string, attachmentIds: string[] = []) {
    return request<{ content: string; context_id: string | null; api_cost_usd: number; billing_mode: "owner" | "caller"; billed_to: "agent_owner" | "caller"; provider: "openrouter" | "openai" | null }>(`/api/remote-agents/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, attachment_ids: attachmentIds }),
    });
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
  listGuardrails() { return request<Guardrail[]>("/api/guardrails"); },
  createGuardrail(body: GuardrailInput) { return request<Guardrail>("/api/guardrails", { method: "POST", body: JSON.stringify(body) }); },
  updateGuardrail(id: string, body: GuardrailInput) { return request<Guardrail>(`/api/guardrails/${id}`, { method: "PUT", body: JSON.stringify(body) }); },
  deleteGuardrail(id: string) { return request<void>(`/api/guardrails/${id}`, { method: "DELETE" }); },
  listVisualModels() { return request<VisualModel[]>("/api/visual-models"); },
  createVisualModel(body: VisualModelInput) { return request<VisualModel>("/api/visual-models", { method: "POST", body: JSON.stringify(body) }); },
  updateVisualModel(id: string, body: VisualModelInput) { return request<VisualModel>(`/api/visual-models/${id}`, { method: "PUT", body: JSON.stringify(body) }); },
  deleteVisualModel(id: string) { return request<void>(`/api/visual-models/${id}`, { method: "DELETE" }); },
  getVisualDataset(id: string) { return request<VisualDatasetSummary>(`/api/visual-models/${id}/dataset`); },
  uploadVisualDataset(id: string, files: File[], className: string) {
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    if (className) body.append("class_name", className);
    return request<VisualDatasetUploadResult>(`/api/visual-models/${id}/dataset`, { method: "POST", body });
  },
  clearVisualDataset(id: string) { return request<void>(`/api/visual-models/${id}/dataset`, { method: "DELETE" }); },
  startVisualTraining(id: string, body: VisualTrainingInput) { return request<VisualTrainingRun>(`/api/visual-models/${id}/training-runs`, { method: "POST", body: JSON.stringify(body) }); },
  getLatestVisualTraining(id: string) { return request<VisualTrainingRun | null>(`/api/visual-models/${id}/training-runs/latest`); },
  getVisualTrainingRun(id: string) { return request<VisualTrainingRun>(`/api/visual-models/training-runs/${id}`); },
  listVisualModelVersions(id: string) { return request<VisualTrainingRun[]>(`/api/visual-models/${id}/versions`); },
  activateVisualModelVersion(modelId: string, runId: string) { return request<VisualTrainingRun>(`/api/visual-models/${modelId}/versions/${runId}/activate`, { method: "POST" }); },
  evaluateVisualModelVersion(modelId: string, runId: string) { return request<VisualTrainingRun>(`/api/visual-models/${modelId}/versions/${runId}/evaluate`, { method: "POST" }); },
  getVisualTrainingDevices() { return request<VisualComputeDevice[]>("/api/visual-models/training-devices"); },
  predictVisualModel(id: string, image: File) {
    const body = new FormData();
    body.append("image", image);
    return request<VisualPrediction>(`/api/visual-models/${id}/predict`, { method: "POST", body });
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
