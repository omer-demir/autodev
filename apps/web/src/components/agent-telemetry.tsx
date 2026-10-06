"use client";

import { useState } from "react";
import { Activity, Clock3, Coins, Cpu, MessageSquareText, RefreshCw, ShieldCheck, Timer, Wrench } from "lucide-react";
import type { AgentTelemetry, AgentTelemetryRun } from "@/lib/types";

function duration(value: number | null) {
  if (value === null) return "Unavailable";
  if (value < 1000) return `${value} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1000)}s`;
}

function number(value: number) {
  return new Intl.NumberFormat("en-US", { notation: value > 9999 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function cost(value: number | null) {
  if (value === null) return "Not configured";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 }).format(value);
}

function Metric({ label, value, note, icon: Icon, tone = "text-teal-300" }: { label: string; value: string; note: string; icon: typeof Activity; tone?: string }) {
  return <div className="rounded-xl border border-white/[.07] bg-black/15 p-4">
    <div className="flex items-center justify-between"><span className="text-[10px] font-medium uppercase tracking-[.16em] text-slate-600">{label}</span><Icon className={`size-4 ${tone}`} /></div>
    <div className="mt-3 text-xl font-semibold text-slate-100">{value}</div>
    <p className="mt-1 text-[10px] leading-4 text-slate-600">{note}</p>
  </div>;
}

function EmptyTelemetry() {
  return <div className="grid min-h-96 place-items-center rounded-xl border border-dashed border-white/[.08] bg-black/10 text-center">
    <div><Activity className="mx-auto size-7 text-slate-700" /><p className="mt-3 text-sm text-slate-400">No runs recorded for this agent.</p><p className="mt-1 text-xs text-slate-600">Telemetry appears after the agent starts a task.</p></div>
  </div>;
}

function RunDetails({ run }: { run: AgentTelemetryRun }) {
  const maxElapsed = Math.max(run.duration_ms, 1);
  return <div className="space-y-4">
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <Metric label="Run duration" value={duration(run.duration_ms)} note={`${run.status} · ${run.phase}`} icon={Timer} />
      <Metric label="Tokens" value={run.totals.tokenized_calls ? number(run.totals.input_tokens + run.totals.output_tokens) : "Unavailable"} note={`${number(run.totals.input_tokens)} input · ${number(run.totals.output_tokens)} output`} icon={Cpu} tone="text-blue-300" />
      <Metric label="Estimated cost" value={cost(run.totals.estimated_cost_usd)} note={`${run.totals.priced_calls}/${run.totals.model_calls} calls priced`} icon={Coins} tone="text-amber-300" />
      <Metric label="Safety" value={`${run.safety.denied_actions} denied`} note={`${run.safety.allowed_actions} allowed · ${run.safety.fallbacks} fallbacks`} icon={ShieldCheck} tone={run.safety.denied_actions ? "text-red-300" : "text-emerald-300"} />
    </div>

    <section className="rounded-xl border border-white/[.07] bg-black/10 p-4">
      <h3 className="text-xs font-semibold text-slate-200">Phase timing</h3>
      <div className="mt-4 space-y-3">{run.phase_timings.length ? run.phase_timings.map((item) => <div key={item.phase} className="grid grid-cols-[100px_1fr_70px] items-center gap-3 text-[11px]"><span className="text-slate-500">{item.phase}</span><div className="h-1.5 overflow-hidden rounded-full bg-white/[.05]"><div className="h-full rounded-full bg-teal-300/70" style={{ width: `${Math.max(2, item.duration_ms / run.duration_ms * 100)}%` }} /></div><span className="text-right font-mono text-slate-500">{duration(item.duration_ms)}</span></div>) : <p className="text-xs text-slate-600">Phase timing requires at least two run events.</p>}</div>
    </section>

    <details open className="group rounded-xl border border-white/[.07] bg-black/10">
      <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold text-slate-200">Model calls · {run.model_calls.length}</summary>
      <div className="overflow-x-auto border-t border-white/[.06]"><table className="w-full min-w-[720px] text-left text-[11px]"><thead className="text-slate-600"><tr><th className="px-4 py-3">Call</th><th>Provider / model</th><th>Tokens in → out</th><th>Latency</th><th>Cost</th><th>Route</th></tr></thead><tbody>{run.model_calls.map((call) => <tr key={`${call.sequence}-${call.created_at}`} className="border-t border-white/[.04]"><td className="px-4 py-3 font-mono text-slate-500">#{call.sequence}</td><td><span className="text-slate-300">{call.provider}</span><span className="text-slate-600"> / {call.model}</span></td><td className="font-mono text-slate-400">{call.input_tokens === null ? "—" : number(call.input_tokens)} → {call.output_tokens === null ? "—" : number(call.output_tokens)}</td><td className="font-mono text-slate-400">{duration(call.latency_ms)}</td><td title={call.cost_basis} className="font-mono text-slate-400">{cost(call.cost_usd)}</td><td className={call.fallback ? "text-amber-300" : "text-emerald-300"}>{call.fallback ? "fallback" : "primary"}</td></tr>)}</tbody></table>{!run.model_calls.length && <p className="p-4 text-xs text-slate-600">No completed model calls.</p>}</div>
    </details>

    <div className="grid gap-4 xl:grid-cols-2">
      <details className="rounded-xl border border-white/[.07] bg-black/10">
        <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold text-slate-200">Tool latency · {run.tools.length}</summary>
        <div className="max-h-80 overflow-auto border-t border-white/[.06]">{run.tools.map((tool) => <div key={`${tool.sequence}-${tool.created_at}`} className="flex items-center gap-3 border-b border-white/[.04] px-4 py-3 text-[11px]"><Wrench className="size-3 text-violet-300" /><span className="min-w-0 flex-1 truncate text-slate-300">{tool.name}<span className="ml-2 text-slate-600">{tool.capability}</span></span><span className="font-mono text-slate-500">{duration(tool.latency_ms)}</span></div>)}{!run.tools.length && <p className="p-4 text-xs text-slate-600">No completed tools.</p>}</div>
      </details>
      <details className="rounded-xl border border-white/[.07] bg-black/10">
        <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold text-slate-200">Guardrails and safety · {run.safety.guardrails.length}</summary>
        <div className="max-h-80 overflow-auto border-t border-white/[.06]">{run.safety.guardrails.map((item, index) => <div key={`${item.type}-${item.created_at}-${index}`} className="border-b border-white/[.04] px-4 py-3"><div className="flex items-center justify-between gap-2 text-[11px]"><span className={item.severity === "error" || item.type.includes("denied") ? "text-red-300" : item.type.includes("allowed") ? "text-emerald-300" : "text-amber-300"}>{item.title}</span><span className="font-mono text-slate-600">{item.policy || item.type}</span></div><p className="mt-1 text-[10px] leading-4 text-slate-600">{item.detail}</p></div>)}{!run.safety.guardrails.length && <p className="p-4 text-xs text-slate-600">No guardrail decisions recorded.</p>}</div>
      </details>
    </div>

    <details className="rounded-xl border border-white/[.07] bg-black/10">
      <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold text-slate-200">Detailed agent messages · {run.messages.length}</summary>
      <div className="max-h-[520px] space-y-3 overflow-auto border-t border-white/[.06] p-4">{run.messages.map((message) => <article key={message.id} className={`rounded-lg border p-3 ${message.role === "user" ? "border-blue-300/10 bg-blue-300/[.03]" : "border-teal-300/10 bg-teal-300/[.03]"}`}><header className="flex justify-between text-[10px] uppercase tracking-wide"><span className={message.role === "user" ? "text-blue-300" : "text-teal-300"}>{message.role}</span><time className="text-slate-600">{new Date(message.created_at).toLocaleString()}</time></header><p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{message.content}</p></article>)}{!run.messages.length && <p className="text-xs text-slate-600">No persisted agent or developer messages.</p>}</div>
    </details>

    <details className="rounded-xl border border-white/[.07] bg-black/10">
      <summary className="cursor-pointer list-none px-4 py-3 text-xs font-semibold text-slate-200">Event timeline drill-down · {run.timeline.length}</summary>
      <div className="max-h-[560px] overflow-auto border-t border-white/[.06] p-4">{run.timeline.map((event) => <div key={event.id} className="grid grid-cols-[76px_14px_1fr] gap-3 pb-4 text-[11px]"><span className="text-right font-mono text-slate-600">+{duration(event.elapsed_ms)}</span><div className="relative"><span className={`absolute left-1 top-1 size-2 rounded-full ${event.severity === "error" ? "bg-red-300" : event.severity === "warning" ? "bg-amber-300" : "bg-teal-300"}`} /><span className="absolute bottom-[-16px] left-[7px] top-3 w-px bg-white/[.07]" /></div><div><div className="flex items-center justify-between gap-2"><span className="text-slate-300">{event.title}</span><span className="font-mono text-[9px] text-slate-700">{event.type}</span></div>{event.detail && <p className="mt-1 line-clamp-3 whitespace-pre-wrap leading-4 text-slate-600">{event.detail}</p>}<div className="mt-2 h-px bg-white/[.04]"><div className="h-px bg-teal-300/30" style={{ width: `${event.elapsed_ms / maxElapsed * 100}%` }} /></div></div></div>)}</div>
    </details>
  </div>;
}

export function SessionObservabilityReport({ run }: { run: AgentTelemetryRun }) {
  return <div className="space-y-5">
    <div><h2 className="text-sm font-semibold">Session observability</h2><p className="mt-1 text-xs text-slate-600">A product-level report for this agent session. Infrastructure details remain in Grafana.</p></div>
    {run.trace_id && <div className="rounded-lg border border-teal-300/10 bg-teal-300/[.03] px-4 py-3 text-[11px] text-slate-500">Trace <span className="ml-2 font-mono text-teal-300">{run.trace_id}</span></div>}
    <RunDetails run={run} />
  </div>;
}

export function AgentTelemetryPanel({ telemetry, loading, error, onRefresh }: { telemetry: AgentTelemetry | null; loading: boolean; error: string; onRefresh: () => void }) {
  const [selectedTaskId, setSelectedTaskId] = useState("");
  if (loading && !telemetry) return <div className="grid min-h-96 place-items-center text-sm text-slate-500"><Activity className="mr-2 inline size-4 animate-pulse" />Loading run telemetry…</div>;
  if (error && !telemetry) return <div className="rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{error}</div>;
  if (!telemetry || !telemetry.runs.length) return <EmptyTelemetry />;
  const selected = telemetry.runs.find((run) => run.task_id === selectedTaskId) || telemetry.runs[0];
  const summary = telemetry.summary;
  return <div className="space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-sm font-semibold">Run telemetry</h2><p className="mt-1 text-xs text-slate-600">Operational observability aggregated from persisted task evidence.</p></div><button onClick={onRefresh} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-white/[.08] px-3 py-2 text-xs text-slate-400 hover:text-teal-300"><RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />Refresh</button></div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      <Metric label="Runs" value={String(summary.runs)} note={`${summary.completed_runs} completed · ${summary.failed_runs} failed`} icon={Activity} />
      <Metric label="Total tokens" value={summary.tokenized_calls ? number(summary.input_tokens + summary.output_tokens) : "Unavailable"} note={`${summary.tokenized_calls}/${summary.model_calls} calls reported usage`} icon={Cpu} tone="text-blue-300" />
      <Metric label="Estimated cost" value={cost(summary.estimated_cost_usd)} note={`${summary.priced_calls}/${summary.model_calls} calls · ${telemetry.pricing.status}`} icon={Coins} tone="text-amber-300" />
      <Metric label="Average run" value={duration(summary.average_duration_ms)} note={`${summary.model_calls} model · ${summary.tool_calls} tool calls`} icon={Clock3} tone="text-violet-300" />
      <Metric label="Guardrails" value={`${summary.denied_actions} denied`} note={`${summary.fallbacks} fallbacks · ${summary.model_errors} errors`} icon={ShieldCheck} tone={summary.denied_actions || summary.model_errors ? "text-red-300" : "text-emerald-300"} />
    </div>
    <div className="rounded-lg border border-amber-300/10 bg-amber-300/[.03] px-4 py-3 text-[10px] leading-4 text-amber-100/70"><strong className="text-amber-200">Cost coverage:</strong> {telemetry.pricing.note} Missing provider usage or pricing is shown as unavailable, never as zero.</div>
    <div className="flex flex-wrap gap-2">{telemetry.runs.map((run) => <button key={run.task_id} onClick={() => setSelectedTaskId(run.task_id)} className={`rounded-lg border px-3 py-2 text-left text-xs ${selected.task_id === run.task_id ? "border-teal-300/30 bg-teal-300/[.06] text-teal-200" : "border-white/[.07] bg-black/10 text-slate-500"}`}><span className="font-mono">{run.task_id}</span><span className="ml-2">{duration(run.duration_ms)}</span></button>)}</div>
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500"><MessageSquareText className="size-3" /><span className="text-slate-300">{selected.title}</span><span>·</span><span>{new Date(selected.started_at).toLocaleString()}</span>{selected.trace_id && <><span>·</span><a className="font-mono text-teal-300 hover:underline" href={`http://localhost:3001/explore?left=${encodeURIComponent(JSON.stringify({ datasource: "Tempo", queries: [{ query: selected.trace_id, queryType: "traceql" }] }))}`} target="_blank" rel="noreferrer" title={selected.trace_id}>Trace {selected.trace_id.slice(0, 12)}…</a></>}</div>
    <RunDetails run={selected} />
  </div>;
}
