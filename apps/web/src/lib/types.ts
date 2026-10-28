export type TaskStatus =
  | "DRAFT"
  | "INTAKE"
  | "PLANNING"
  | "IMPLEMENTATION"
  | "TESTING"
  | "SECURITY"
  | "REVIEW"
  | "AWAITING_MODEL"
  | "AWAITING_APPROVAL"
  | "DONE"
  | "FAILED"
  | "CANCELLED";

export interface Project {
  id: number;
  name: string;
  repository_path: string;
  source_type: "local" | "github" | "empty";
  repository_url: string | null;
  default_branch: string | null;
  connector_id: string | null;
  transport: "ssh" | "https";
}
export interface Connector {
  id: string;
  provider: "github" | "gitlab" | "azure_devops";
  name: string;
  auth_method: string;
  status: "REGISTERING" | "PENDING_INSTALLATION" | "ACTIVE" | "FAILED";
  account_login: string | null;
  metadata: Record<string, string | number | boolean | null>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}
export interface ConnectorAccount {
  login: string;
  type: string;
  installation_id: number;
  repository_selection: string;
}
export interface Task {
  id: string;
  project_id: number;
  title: string;
  description: string;
  status: TaskStatus;
  phase: string;
  progress: number;
  workflow_id: string;
  agent_id: string;
  branch: string;
  mode: "change" | "assessment";
  verbose_logging: boolean;
  created_at: string;
  updated_at: string;
}
export interface TaskPage {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
  counts: {
    active: number;
    awaiting_approval: number;
    done: number;
    failed: number;
  };
}
export interface AuthUser {
  user_id: string;
  organization_id: string;
  role: string;
  email: string | null;
  auth_mode: "local" | "oidc";
}
export interface OrganizationMember {
  user_id: string;
  email: string | null;
  display_name: string | null;
  role: string;
  created_at: string;
}
export interface TimelineEvent {
  id: number;
  task_id: string;
  type: string;
  title: string;
  detail: string;
  severity: "info" | "warning" | "error";
  data: Record<string, unknown>;
  created_at: string;
}
export interface Approval {
  id: string;
  task_id: string;
  action: string;
  scope: Record<string, string>;
  status: string;
  reason: string;
  created_at: string;
}
export interface Sandbox {
  id: string;
  task_id: string;
  provider: string;
  status: string;
  workspace: string;
  network_policy: string;
  container_id: string | null;
  host_workspace: string | null;
  created_at: string;
}
export interface SecurityFinding {
  task_id: string;
  title: string;
  status: string;
  created_at: string;
  high: number;
  medium: number;
  low: number;
  scanners: Record<string, string>;
}
export interface SecurityOverview {
  summary: Record<"high" | "medium" | "low", number>;
  findings: SecurityFinding[];
}
export interface GovernanceOverview {
  summary: { pending_approvals: number; allowed: number; denied: number };
  approvals: Approval[];
  decisions: TimelineEvent[];
}
export interface EvidenceSummary {
  task_id: string;
  title: string;
  status: TaskStatus;
  updated_at: string;
  artifact_kinds: string[];
}
export interface Message {
  id: number;
  task_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}
export interface WorkflowPhase {
  id: string;
  status: TaskStatus;
  label: string;
  progress: number | "inherit";
}
export interface WorkflowStage {
  id: string;
  agent: string;
  responsibility: string;
  inputs?: string[];
  outputs: string[];
}
export interface WorkflowDefinition {
  name: string;
  version: string;
  phases: WorkflowPhase[];
  stages?: WorkflowStage[];
}
export interface WorkflowStageRun {
  status: "running" | "completed" | "failed";
  agent_id: string;
  responsibility?: string;
  inputs?: string[];
  outputs?: string[];
  error?: string;
}
export interface WorkflowRun {
  workflow_id: string;
  workflow_version: string;
  status: "running" | "completed" | "failed";
  stages: Record<string, WorkflowStageRun>;
  error?: string;
}
export interface ChangeTreeEntry {
  name: string;
  path: string;
  kind: "folder" | "file";
  status?: string;
  file_count: number;
  additions: number;
  deletions: number;
}
export interface TaskChangesDirectory {
  path: string;
  entries: ChangeTreeEntry[];
  file_count: number;
  revision: string;
}
export interface TaskChangeDiff {
  path: string;
  diff: string;
  revision: string;
}
export interface Artifacts {
  plan?: { requirements: string[]; steps: string[]; acceptance: string[] };
  changes?: {
    files: {
      path: string;
      status: string;
      additions: number;
      deletions: number;
      patch?: string;
    }[];
    diff: string;
  };
  tests?: {
    passed: number;
    failed: number;
    skipped: number;
    duration: number;
    output: string;
    commands?: string[][];
  };
  security?: {
    high: number;
    medium: number;
    low: number;
    scanners: Record<string, string>;
  };
  "workflow-definition"?: {
    workflow_id: string;
    workflow_version: string;
    definition: WorkflowDefinition;
  };
  "workflow-run"?: WorkflowRun;
}
export interface TaskDetail {
  task: Task;
  project: Project;
  events: TimelineEvent[];
  artifacts: Artifacts;
  sandbox: Sandbox | null;
  approval: Approval | null;
  messages: Message[];
  model_recovery: ModelRecoveryRequest | null;
}
export interface ModelRecoveryRequest {
  task_id: string;
  provider: string;
  model: string;
  fallback_provider: string;
  fallback_model: string;
  error: string;
  created_at: string;
  attempts: number;
}
export interface GitHubRepository {
  name: string;
  full_name: string;
  private: boolean;
  clone_url: string;
  ssh_url: string | null;
  html_url: string | null;
  owner: string | null;
  default_branch: string | null;
  updated_at: string;
}
export interface RuntimeStatus {
  mode: string;
  model_provider: string;
  active_model_provider: string;
  model_fallback_active: boolean;
  configured_model: string;
  ollama_reachable: boolean;
  model_request_timeout_seconds: number;
  agent_turn_timeout_seconds: number;
  model_recovery_timeout_seconds: number;
  sandbox_command_timeout_seconds: number;
  models: {
    name: string;
    size?: number | null;
    provider: string;
    fallback: boolean;
  }[];
  model_available: boolean;
  model_error: string | null;
  sandbox_provider: string;
  sandbox_available: boolean;
  sandbox: {
    ready: boolean;
    provider?: string;
    endpoint?: string;
    error?: string;
  };
  docker_available: boolean;
  docker: {
    cli: boolean;
    daemon: boolean;
    ready: boolean;
    error?: string;
  } | null;
  github_authenticated: boolean;
  github_login: string | null;
  github_auth_method: "github_app" | "oauth" | "environment" | null;
  github_app_slug: string | null;
  github_installations: {
    id: number;
    account: string;
    repository_selection: string;
  }[];
  github_app_configured: boolean;
  github_oauth_configured: boolean;
}
export interface DashboardData {
  metrics: Record<
    | "active_tasks"
    | "awaiting_approval"
    | "running_agents"
    | "security_findings"
    | "sandboxes_ready",
    number
  >;
  tasks: Task[];
}
export interface RegistryDefinition {
  kind:
    | "agents"
    | "skills"
    | "mcp"
    | "workflows"
    | "policies"
    | "evaluation-suites"
    | "harnesses"
    | "capability-catalogs";
  id: string;
  raw: string;
  data: Record<string, unknown>;
}
export interface RuntimeCapabilities {
  capabilities: string[];
  resolvers: string[];
}
export interface SessionSummary {
  id: string;
  task_id: string;
  title: string;
  status: TaskStatus;
  agent_id: string;
  workspace_persisted: boolean;
  updated_at: string;
}
export interface SessionHistory {
  id: string;
  task: Task;
  workspace: string | null;
  events: TimelineEvent[];
  messages: Message[];
  outputs: Record<string, unknown>;
}
export interface ChatSessionSummary {
  id: string;
  task_id: string;
  title: string;
  status: TaskStatus | "PROCESSING";
  project_id: number | null;
  agent_ids: string[];
  skill_ids: string[];
  model_name: string | null;
  model_provider?: string | null;
  approval_strategy: "agent_policy";
  updated_at: string;
}
export interface ChatAttachment {
  id: string;
  name: string;
  media_type: string;
  url: string;
}
export interface ChatMessage {
  id: number;
  task_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  attachments?: ChatAttachment[];
  model_provider?: string | null;
  model_name?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  estimated_cost_usd?: number | null;
  cost_note?: string | null;
}
export interface ChatSession {
  chat: ChatSessionSummary;
  task: { id: string; project_id: number | null; status: TaskStatus } | null;
  messages: ChatMessage[];
  events: TimelineEvent[];
  error?: string | null;
}
export interface ChatOptions {
  agents: { id: string; name: string; description: string; skills: string[] }[];
  skills: { id: string; name: string; description: string }[];
  models: { name: string; provider: string }[];
  approval_strategies: { id: "agent_policy"; label: string }[];
}
export interface ChatStartResult {
  chat: ChatSessionSummary;
  status: "started" | "completed" | "failed";
  execution_job_id: string | null;
  messages: ChatMessage[];
}
export interface ChatFollowUpResult {
  chat_id: string;
  status: "started";
  session_id: string;
  agent_id: string;
}
export interface GatewayStatus {
  streamable_http: string;
  sse: string;
  messages: string;
  tools: string[];
  auth_mode: string;
  organization_id: string;
}
export interface EvaluationRun {
  id: string;
  agent_id: string;
  agent_version: string;
  suite_id: string;
  suite_version: string;
  status: string;
  evaluator: string;
  overall_score: number;
  scores: Record<string, number | null>;
  results: Record<string, unknown>[];
  dataset_id?: string | null;
  metrics?: Record<string, unknown>;
  comparison?: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: string;
}
export interface EvaluationEvent {
  id: number;
  run_id: string;
  organization_id: string;
  adapter: string | null;
  scenario_id: string | null;
  type: string;
  title: string;
  detail: string;
  severity: string;
  data: Record<string, unknown>;
  created_at: string;
}
export interface EvaluationArtifact {
  path: string;
  size_bytes: number;
  preview: string | null;
}
export interface EvaluationArtifacts {
  run_id: string;
  files: EvaluationArtifact[];
}
export interface EvaluationDataset {
  id: string;
  dataset_name: string;
  version: number;
  agent_id: string;
  agent_version: string;
  suite_id: string;
  suite_version: string;
  status: "DRAFT" | "REVIEWED" | "FROZEN";
  scenarios: Record<string, unknown>[];
  adapter_specs: Record<string, unknown>;
  content_hash: string | null;
  generated_by: string;
  reviewed_by: string | null;
  frozen_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface EvaluationDatasetPage {
  items: EvaluationDataset[];
  total: number;
  page: number;
  page_size: number;
}
export interface BehavioralEvaluationReadiness {
  ready: boolean;
  adapters: Record<
    "native" | "vally" | "waza",
    {
      ready: boolean;
      detail: string;
      executable?: string | null;
    }
  >;
}
export interface EvaluationModelCatalog {
  provider: "copilot" | "ollama";
  default_model: string | null;
  models: {
    name: string;
    id?: string;
    provider: string;
    size?: number | null;
    automatic?: boolean;
  }[];
}

export interface AgentTelemetryModelCall {
  sequence: number;
  provider: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  cost_usd: number | null;
  cost_basis: string;
  fallback: boolean;
  created_at: string;
}
export interface AgentTelemetryToolCall {
  sequence: number;
  name: string;
  capability: string | null;
  latency_ms: number | null;
  status: string;
  created_at: string;
}
export interface AgentTelemetryGuardrail {
  type: string;
  title: string;
  detail: string;
  severity: string;
  capability: string | null;
  decision: string | null;
  policy: string | null;
  created_at: string;
}
export interface AgentTelemetryRun {
  task_id: string;
  title: string;
  status: TaskStatus;
  phase: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  trace_id: string | null;
  model_calls: AgentTelemetryModelCall[];
  tools: AgentTelemetryToolCall[];
  messages: { id: number; role: string; content: string; created_at: string }[];
  timeline: {
    id: number;
    type: string;
    title: string;
    detail: string;
    severity: string;
    created_at: string;
    elapsed_ms: number;
    trace_id: string | null;
    span_id: string | null;
  }[];
  phase_timings: { phase: string; duration_ms: number }[];
  safety: {
    allowed_actions: number;
    denied_actions: number;
    fallbacks: number;
    model_errors: number;
    security: {
      high: number;
      medium: number;
      low: number;
      scanners: Record<string, string>;
    };
    approvals: {
      id: string;
      action: string;
      status: string;
      wait_ms: number | null;
      created_at: string;
      decided_at: string | null;
    }[];
    guardrails: AgentTelemetryGuardrail[];
  };
  totals: {
    input_tokens: number;
    output_tokens: number;
    tokenized_calls: number;
    model_calls: number;
    tool_calls: number;
    estimated_cost_usd: number | null;
    priced_calls: number;
    unpriced_calls: number;
  };
}
export type TaskObservability = AgentTelemetryRun;
export interface AgentTelemetry {
  agent_id: string;
  generated_at: string;
  pricing: {
    currency: "USD";
    status: "complete" | "partial" | "unavailable";
    note: string;
  };
  summary: {
    runs: number;
    completed_runs: number;
    failed_runs: number;
    total_duration_ms: number;
    average_duration_ms: number;
    model_calls: number;
    tool_calls: number;
    input_tokens: number;
    output_tokens: number;
    tokenized_calls: number;
    estimated_cost_usd: number | null;
    priced_calls: number;
    unpriced_calls: number;
    denied_actions: number;
    fallbacks: number;
    model_errors: number;
    providers: Record<string, number>;
  };
  runs: AgentTelemetryRun[];
}
