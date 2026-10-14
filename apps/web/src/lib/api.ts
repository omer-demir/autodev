import type { AgentTelemetry, AuthUser, BehavioralEvaluationReadiness, Connector, ConnectorAccount, DashboardData, EvaluationArtifacts, EvaluationDataset, EvaluationDatasetPage, EvaluationEvent, EvaluationModelCatalog, EvaluationRun, EvidenceSummary, GatewayStatus, GitHubRepository, GovernanceOverview, OrganizationMember, Project, RegistryDefinition, RuntimeCapabilities, RuntimeStatus, Sandbox, SecurityOverview, SessionHistory, SessionSummary, Task, TaskChangeDiff, TaskChangesDirectory, TaskDetail, TaskObservability, TaskPage } from "./types";

// Native development stays same-origin through the Next.js /api rewrite. This avoids
// remote-workspace localhost forwarding and browser CORS/connection failure modes.
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly path: string,
    readonly kind: "timeout" | "network" | "http",
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function describeApiError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

async function call<T>(path: string, init?: RequestInit, timeoutMs = 15_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  init?.signal?.addEventListener("abort", abort, { once: true });
  try {
    let response: Response;
    try {
      response = await fetch(`${API_URL}${path}`, {
        ...init,
        signal: controller.signal,
        credentials: "include",
        headers: { "Content-Type": "application/json", ...init?.headers },
        cache: "no-store",
      });
    } catch (error) {
      if (controller.signal.aborted && !init?.signal?.aborted) {
        throw new ApiError(`Request to ${path} timed out after ${Math.round(timeoutMs / 1000)}s.`, path, "timeout");
      }
      throw new ApiError(`Cannot reach ${path}: ${error instanceof Error ? error.message : String(error)}`, path, "network");
    }
    if (!response.ok) {
      const detail = (await response.text()).trim();
      throw new ApiError(`${path} returned HTTP ${response.status}${detail ? `: ${detail}` : ""}`, path, "http", response.status);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } finally {
    window.clearTimeout(timeout);
    init?.signal?.removeEventListener("abort", abort);
  }
}

export const api = {
  me: () => call<AuthUser>("/api/auth/me"),
  logout: () => call<void>("/api/auth/logout", { method: "POST" }),
  members: () => call<OrganizationMember[]>("/api/admin/members"),
  createMember: (body: { user_id: string; email?: string; display_name?: string; role: string }) =>
    call<OrganizationMember>("/api/admin/members", { method: "POST", body: JSON.stringify(body) }),
  updateMember: (userId: string, role: string) => call<OrganizationMember>(`/api/admin/members/${encodeURIComponent(userId)}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  deleteMember: (userId: string) => call<void>(`/api/admin/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),
  dashboard: () => call<DashboardData>("/api/dashboard"),
  tasks: (options: { status?: string; query?: string; sort_by?: string; sort_order?: string; page?: number; page_size?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(options).forEach(([key, value]) => {
      if (value !== undefined && value !== "") params.set(key, String(value));
    });
    return call<TaskPage>(`/api/tasks?${params.toString()}`);
  },
  projects: () => call<Project[]>("/api/projects"),
  createProject: (body: {
    name: string; repository_path: string; source_type: Project["source_type"];
    repository_url: string | null; default_branch: string | null;
    connector_id?: string | null; transport?: "ssh" | "https";
  }) =>
    call<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  deleteProject: (id: number) => call<void>(
    `/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" },
  ),
  connectors: () => call<Connector[]>("/api/connectors"),
  connectorAccounts: (id: string) => call<{ connector: Connector; accounts: ConnectorAccount[] }>(
    `/api/connectors/${encodeURIComponent(id)}/accounts`,
  ),
  connectorRepositories: (id: string, account: string, query = "") => {
    const params = new URLSearchParams({ account });
    if (query) params.set("query", query);
    return call<{ connector_id: string; account: string; repositories: GitHubRepository[] }>(
      `/api/connectors/${encodeURIComponent(id)}/repositories?${params.toString()}`,
    );
  },
  verifyConnector: (id: string) => call<{ verified: boolean; app: string; status: string }>(
    `/api/connectors/${encodeURIComponent(id)}/verify`, { method: "POST" },
  ),
  deleteConnector: (id: string) => call<void>(
    `/api/connectors/${encodeURIComponent(id)}`, { method: "DELETE" },
  ),
  githubRepositories: (owner: string) =>
    call<{ owner: string; repositories: GitHubRepository[]; authenticated: boolean }>(`/api/connectors/github/repos?owner=${encodeURIComponent(owner)}`),
  githubRepository: (url: string) =>
    call<GitHubRepository>("/api/connectors/github/repo", { method: "POST", body: JSON.stringify({ url }) }),
  disconnectGitHub: () => call<{ authenticated: boolean; method: string | null }>(
    "/api/connectors/github/disconnect", { method: "POST" },
  ),
  runtime: () => call<RuntimeStatus>("/api/runtime"),
  gateway: () => call<GatewayStatus>("/api/gateway"),
  sessions: () => call<SessionSummary[]>("/api/sessions"),
  session: (id: string) => call<SessionHistory>(`/api/sessions/${encodeURIComponent(id)}`),
  continueSession: (id: string, content: string, agent_id?: string) =>
    call<{ status: string; session_id: string; agent_id: string }>(`/api/sessions/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ content, agent_id }) }),
  publishTask: (id: string, branch: string, create_pull_request: boolean) =>
    call<{ status: string; approval_id: string; actions: string[] }>(`/api/tasks/${encodeURIComponent(id)}/publish`, { method: "POST", body: JSON.stringify({ branch, create_pull_request }) }),
  task: (id: string) => call<TaskDetail>(`/api/tasks/${id}`),
  taskChanges: (id: string, path = "") => {
    const params = new URLSearchParams();
    if (path) params.set("path", path);
    const query = params.size ? `?${params.toString()}` : "";
    return call<TaskChangesDirectory>(`/api/tasks/${encodeURIComponent(id)}/changes${query}`);
  },
  taskChangeDiff: (id: string, path: string) => {
    const params = new URLSearchParams({ path });
    return call<TaskChangeDiff>(`/api/tasks/${encodeURIComponent(id)}/changes/diff?${params.toString()}`);
  },
  taskObservability: (id: string) => call<TaskObservability>(`/api/tasks/${id}/observability`),
  resolveModelRecovery: (id: string, action: "retry" | "change_model" | "fallback" | "cancel", model?: string) =>
    call(`/api/tasks/${id}/model-recovery`, { method: "POST", body: JSON.stringify({ action, model }) }),
  createTask: (body: { project_id: number; title: string; description: string; model_name?: string; workflow_id?: string; agent_id?: string; mode?: "change" | "assessment"; verbose_logging?: boolean }) =>
    call<Task>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  runTask: (id: string) => call(`/api/tasks/${id}/run`, { method: "POST" }),
  updateTaskMode: (id: string, mode: "change" | "assessment") =>
    call<Task>(`/api/tasks/${id}/mode`, { method: "PATCH", body: JSON.stringify({ mode }) }),
  cancelTask: (id: string) => call(`/api/tasks/${id}/cancel`, { method: "POST" }),
  approve: (id: string) => call(`/api/approvals/${id}/approve`, { method: "POST" }),
  deny: (id: string) => call(`/api/approvals/${id}/deny`, { method: "POST" }),
  sandboxes: () => call<Sandbox[]>("/api/sandboxes"),
  killSandbox: (id: string) => call<Sandbox>(`/api/sandboxes/${id}/kill`, { method: "POST" }),
  security: () => call<SecurityOverview>("/api/security"),
  governance: () => call<GovernanceOverview>("/api/governance"),
  evidence: () => call<EvidenceSummary[]>("/api/evidence"),
  execute: (id: string, command: string) => call<{ output: string; exit_code: number; simulated: boolean }>(
    `/api/sandboxes/${id}/execute`, { method: "POST", body: JSON.stringify({ command }) },
  ),
  steer: (id: string, content: string) => call(`/api/tasks/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  openEditor: (id: string) => call<{ opened: boolean; url?: string; workspace: string }>(`/api/tasks/${id}/open`, { method: "POST" }),
  registry: (kind: RegistryDefinition["kind"]) => call<RegistryDefinition[]>(`/api/registry/${kind}`),
  runtimeCapabilities: () => call<RuntimeCapabilities>("/api/runtime-capabilities"),
  saveDefinition: (kind: RegistryDefinition["kind"], id: string, raw: string) =>
    call<RegistryDefinition>(`/api/registry/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ raw }) }),
  importIntegration: (url: string, kind: "auto" | "agent" | "skill", identifier?: string) =>
    call<RegistryDefinition>("/api/integrations/import", {
      method: "POST",
      body: JSON.stringify({ url, kind, identifier: identifier || undefined }),
    }, 30_000),
  deleteDefinition: (kind: RegistryDefinition["kind"], id: string) =>
    call<void>(`/api/registry/${kind}/${encodeURIComponent(id)}`, { method: "DELETE" }),
  checkDefinition: (kind: RegistryDefinition["kind"], id: string) =>
    call<{ valid: boolean; check: string; detail: string; status_code?: number }>(
      `/api/registry/${kind}/${encodeURIComponent(id)}/check`, { method: "POST" },
    ),
  assignWorkflowStageAgent: (workflowId: string, stageId: string, agent_id: string) =>
    call<RegistryDefinition>(`/api/registry/workflows/${encodeURIComponent(workflowId)}/stages/${encodeURIComponent(stageId)}`, {
      method: "PATCH", body: JSON.stringify({ agent_id }),
    }),
  evaluations: () => call<EvaluationRun[]>("/api/evaluations"),
  evaluation: (id: string) => call<EvaluationRun>(`/api/evaluations/${encodeURIComponent(id)}`),
  cancelEvaluation: (id: string) => call<EvaluationRun>(
    `/api/evaluations/${encodeURIComponent(id)}/cancel`, { method: "POST" },
  ),
  evaluationEvents: (id: string, afterId = 0) => call<EvaluationEvent[]>(`/api/evaluations/${encodeURIComponent(id)}/events?after_id=${afterId}`),
  evaluationArtifacts: (id: string) => call<EvaluationArtifacts>(`/api/evaluations/${encodeURIComponent(id)}/artifacts`),
  evaluationDatasets: () => call<EvaluationDataset[]>("/api/evaluation-datasets"),
  evaluationDataset: (id: string) => call<EvaluationDataset>(`/api/evaluation-datasets/${encodeURIComponent(id)}`),
  evaluationDatasetVersions: (id: string) => call<EvaluationDataset[]>(`/api/evaluation-datasets/${encodeURIComponent(id)}/versions`),
  evaluationDatasetCatalog: (options: { query?: string; status?: string; agent_id?: string; page?: number; page_size?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(options).forEach(([key, value]) => {
      if (value !== undefined && value !== "") params.set(key, String(value));
    });
    return call<EvaluationDatasetPage>(`/api/evaluation-datasets/catalog?${params.toString()}`);
  },
  behavioralEvaluationReadiness: () => call<BehavioralEvaluationReadiness>("/api/evaluations/behavioral/readiness"),
  evaluationModels: (provider: "copilot" | "ollama") => call<EvaluationModelCatalog>(
    `/api/evaluations/models?provider=${encodeURIComponent(provider)}`,
  ),
  createEvaluationDataset: (agent_id: string) =>
    call<EvaluationDataset>("/api/evaluation-datasets", { method: "POST", body: JSON.stringify({ agent_id }) }),
  ensureEvaluationBaselines: () => call<EvaluationDataset[]>(
    "/api/evaluation-datasets/baselines", { method: "POST" },
  ),
  reviewEvaluationDataset: (
    id: string, scenarios: Record<string, unknown>[], reviewed_by: string,
  ) => call<EvaluationDataset>(`/api/evaluation-datasets/${id}`, {
    method: "PUT", body: JSON.stringify({ scenarios, reviewed_by }),
  }),
  freezeEvaluationDataset: (id: string, reviewed_by: string) =>
    call<EvaluationDataset>(`/api/evaluation-datasets/${id}/freeze`, { method: "POST", body: JSON.stringify({ reviewed_by }) }),
  createEvaluationDatasetVersion: (
    id: string, scenarios: Record<string, unknown>[],
  ) => call<EvaluationDataset>(`/api/evaluation-datasets/${id}/versions`, {
    method: "POST", body: JSON.stringify({ scenarios }),
  }),
  runBehavioralEvaluation: (agent_id: string, dataset_id: string, model_provider = "ollama", model_name = "gemma4:e2b", verbose_logging = false) =>
    call<EvaluationRun>("/api/evaluations/behavioral", { method: "POST", body: JSON.stringify({ agent_id, dataset_id, model_provider, model_name, adapters: ["native", "vally", "waza"], verbose_logging }) }),
  runDeclarationCheck: (agent_id: string, dataset_id: string) =>
    call<EvaluationRun>("/api/evaluations/declaration", { method: "POST", body: JSON.stringify({ agent_id, dataset_id }) }, 120_000),
  runSecurityEvaluation: (agent_id: string, include_foundry = true) =>
    call<EvaluationRun>("/api/evaluations/security", { method: "POST", body: JSON.stringify({ agent_id, include_foundry }) }, 120_000),
  promoteAgent: (agentId: string) => call<RegistryDefinition>(`/api/agents/${encodeURIComponent(agentId)}/promote`, { method: "POST" }),
  setAgentEvaluationRequirement: (
    agentId: string, evaluation_required: boolean, reason: string,
  ) => call<RegistryDefinition>(
    `/api/agents/${encodeURIComponent(agentId)}/evaluation-requirement`,
    { method: "PUT", body: JSON.stringify({ evaluation_required, reason }) },
  ),
  agentTelemetry: (agentId: string, limit = 20) => call<AgentTelemetry>(`/api/agents/${encodeURIComponent(agentId)}/telemetry?limit=${limit}`),
};