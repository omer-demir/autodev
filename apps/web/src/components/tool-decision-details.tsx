import { ShieldX } from "lucide-react";
import type { TimelineEvent } from "@/lib/types";

const toolDescriptions: Record<string, string> = {
  list_files: "List a bounded page of repository files.",
  search_text: "Search repository text literally.",
  read_file: "Read a bounded UTF-8 repository file chunk.",
  read_repository_file: "Read a bounded UTF-8 repository file chunk.",
  write_file: "Create or replace a UTF-8 repository file.",
  delete_file: "Delete one repository file.",
  run_command: "Run a governed argument-vector test, build, dependency, or Git command.",
};

const sensitiveArgument = /(?:token|secret|password|passwd|authorization|credential|api[_-]?key)/i;

export function enrichDeniedToolEvents(events: TimelineEvent[]): TimelineEvent[] {
  return events.map((event) => {
    if (!isDeniedToolEvent(event) || text(event.data.tool)) return event;
    const requested = events
      .filter((candidate) => candidate.type === "tool.requested" && candidate.id < event.id)
      .sort((left, right) => right.id - left.id)[0];
    const tool = text(requested?.data.tool) || requested?.title || "Unknown tool";
    const summary = text(requested?.data.request_summary)
      || legacyRequestSummary(tool, requested?.detail, event.data.arguments);
    return {
      ...event,
      data: {
        ...event.data,
        tool,
        tool_description: toolDescriptions[tool] || "Governed workspace operation.",
        request_summary: summary,
      },
    };
  });
}

export function ToolDecisionDetails({
  event,
  compact = false,
}: {
  event: TimelineEvent;
  compact?: boolean;
}) {
  if (!isDeniedToolEvent(event)) return null;
  const tool = text(event.data.tool) || "Unknown tool";
  const description = text(event.data.tool_description);
  const request = text(event.data.request_summary);
  const capability = text(event.data.capability) || "unclassified";
  const policy = text(event.data.policy);
  const provider = text(event.data.provider);
  const agentTier = text(event.data.agent_tier);
  const requiredTier = text(event.data.required_tier);

  return <div className={`mt-2 rounded-lg border border-red-400/10 bg-red-400/[.035] ${compact ? "p-2.5" : "p-3"}`}>
    <div className="flex items-start gap-2">
      <span className="mt-0.5 rounded bg-red-400/10 p-1"><ShieldX className="size-3 text-red-300" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-mono text-[11px] font-medium text-red-200">{tool}</span>
          <span className="rounded bg-white/[.04] px-1.5 py-0.5 font-mono text-[9px] text-slate-500">{capability}</span>
        </div>
        {description && <p className="mt-1 text-[11px] leading-4 text-slate-400">{description}</p>}
        {request && <p className="mt-1.5 break-words font-mono text-[10px] leading-4 text-slate-500">{request}</p>}
      </div>
    </div>
    {!compact && <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-white/[.05] pt-2 text-[9px] uppercase tracking-wide text-slate-600">
      {policy && <span>Policy <strong className="font-mono font-normal text-slate-400">{policy}</strong></span>}
      {provider && <span>Supervisor <strong className="font-mono font-normal text-slate-400">{provider}</strong></span>}
      {agentTier && <span>Tier <strong className="font-mono font-normal text-slate-400">{agentTier}</strong></span>}
      {requiredTier && <span>Required <strong className="font-mono font-normal text-slate-400">{requiredTier}</strong></span>}
    </div>}
  </div>;
}

function isDeniedToolEvent(event: TimelineEvent): boolean {
  return event.type === "tool.denied" || event.type === "runtime_supervision.denied";
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function legacyRequestSummary(tool: string, detail: string | undefined, fallback: unknown): string {
  let argumentsValue: Record<string, unknown> = {};
  try {
    const parsed = detail ? JSON.parse(detail) : fallback;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      argumentsValue = parsed as Record<string, unknown>;
      const nested = argumentsValue.arguments;
      if (nested && typeof nested === "object" && !Array.isArray(nested)) {
        argumentsValue = nested as Record<string, unknown>;
      }
    }
  } catch {
    return "Governed tool request";
  }
  const path = text(argumentsValue.path) || ".";
  if (tool === "run_command") {
    const command = Array.isArray(argumentsValue.arguments)
      ? redactCommandArguments(argumentsValue.arguments).join(" ")
      : "";
    return command ? `Command: ${command.slice(0, 500)}` : "Governed command request";
  }
  if (tool === "write_file") {
    return `Path: ${path} · proposed content: ${text(argumentsValue.content).length} characters`;
  }
  if (tool === "delete_file") return `Path: ${path}`;
  if (tool === "read_file" || tool === "read_repository_file") return `Path: ${path}`;
  if (tool === "search_text") return `Search repository text · path ${path}`;
  if (tool === "list_files") return `List files · path ${path}`;
  return "Governed tool request";
}

function redactCommandArguments(argumentsValue: unknown[]): string[] {
  const redacted: string[] = [];
  let redactNext = false;
  for (const item of argumentsValue.slice(0, 40)) {
    const value = String(item);
    if (redactNext) {
      redacted.push("[REDACTED]");
      redactNext = false;
      continue;
    }
    const separator = value.indexOf("=");
    const key = separator >= 0 ? value.slice(0, separator) : value;
    if (separator >= 0 && sensitiveArgument.test(key)) {
      redacted.push(`${key}=[REDACTED]`);
      continue;
    }
    redacted.push(value);
    if (value.startsWith("-") && sensitiveArgument.test(value)) redactNext = true;
  }
  return redacted;
}
