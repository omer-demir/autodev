import type { AgentTelemetry, BehavioralEvaluationReadiness, DashboardData, EvaluationDataset, EvaluationRun, EvidenceSummary, GatewayStatus, GitHubRepository, GovernanceOverview, Project, RegistryDefinition, RuntimeStatus, Sandbox, SecurityOverview, SessionHistory, SessionSummary, Task, TaskDetail, TaskObservability } from "./types";

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
  dashboard: () => call<DashboardData>("/api/dashboard"),
  tasks: () => call<Task[]>("/api/tasks"),
  projects: () => call<Project[]>("/api/projects"),
  createProject: (body: Omit<Project, "id">) =>
    call<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
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
  taskObservability: (id: string) => call<TaskObservability>(`/api/tasks/${id}/observability`),
  resolveModelRecovery: (id: string, action: "retry" | "change_model" | "fallback" | "cancel", model?: string) =>
    call(`/api/tasks/${id}/model-recovery`, { method: "POST", body: JSON.stringify({ action, model }) }),
  createTask: (body: { project_id: number; title: string; description: string; model_name?: string; agent_id?: string; mode?: "change" | "assessment"; verbose_logging?: boolean }) =>
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
  saveDefinition: (kind: RegistryDefinition["kind"], id: string, raw: string) =>
    call<RegistryDefinition>(`/api/registry/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify({ raw }) }),
  importIntegration: (url: string, kind: "auto" | "agent" | "skill", identifier?: string) =>
    call<RegistryDefinition>("/api/integrations/import", {
      method: "POST",
      body: JSON.stringify({ url, kind, identifier: identifier || undefined }),
    }, 30_000),
  deleteDefinition: (kind: RegistryDefinition["kind"], id: string) =>
    call<void>(`/api/registry/${kind}/${encodeURIComponent(id)}`, { method: "DELETE" }),
  evaluations: () => call<EvaluationRun[]>("/api/evaluations"),
  evaluationDatasets: () => call<EvaluationDataset[]>("/api/evaluation-datasets"),
  behavioralEvaluationReadiness: () => call<BehavioralEvaluationReadiness>("/api/evaluations/behavioral/readiness"),
  createEvaluationDataset: (agent_id: string, suite_id: string) =>
    call<EvaluationDataset>("/api/evaluation-datasets", { method: "POST", body: JSON.stringify({ agent_id, suite_id }) }),
  reviewEvaluationDataset: (id: string, scenarios: Record<string, unknown>[], reviewed_by: string) =>
    call<EvaluationDataset>(`/api/evaluation-datasets/${id}`, { method: "PUT", body: JSON.stringify({ scenarios, reviewed_by }) }),
  freezeEvaluationDataset: (id: string, reviewed_by: string) =>
    call<EvaluationDataset>(`/api/evaluation-datasets/${id}/freeze`, { method: "POST", body: JSON.stringify({ reviewed_by }) }),
  runBehavioralEvaluation: (dataset_id: string, model_name?: string) =>
    call<EvaluationRun>("/api/evaluations/behavioral", { method: "POST", body: JSON.stringify({ dataset_id, model_name, adapters: ["native", "vally", "waza"] }) }),
  runDeclarationCheck: (agent_id: string, suite_id: string) =>
    call<EvaluationRun>("/api/evaluations/declaration", { method: "POST", body: JSON.stringify({ agent_id, suite_id }) }, 120_000),
  runSecurityEvaluation: (agent_id: string, include_foundry = true) =>
    call<EvaluationRun>("/api/evaluations/security", { method: "POST", body: JSON.stringify({ agent_id, include_foundry }) }, 120_000),
  promoteAgent: (agentId: string) => call<RegistryDefinition>(`/api/agents/${encodeURIComponent(agentId)}/promote`, { method: "POST" }),
  agentTelemetry: (agentId: string, limit = 20) => call<AgentTelemetry>(`/api/agents/${encodeURIComponent(agentId)}/telemetry?limit=${limit}`),
};