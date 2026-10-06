"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, GitPullRequest, History, Network, Play, RefreshCw, Send } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { GatewayStatus, RuntimeStatus, SessionHistory, SessionSummary } from "@/lib/types";

const terminal = new Set(["DONE", "FAILED", "CANCELLED"]);

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionHistory | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [gateway, setGateway] = useState<GatewayStatus | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [branch, setBranch] = useState("");
  const [pullRequest, setPullRequest] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [values, runtimeStatus, gatewayStatus] = await Promise.all([
        api.sessions(), api.runtime(), api.gateway(),
      ]);
      setSessions(values); setRuntime(runtimeStatus); setGateway(gatewayStatus);
      setMessage("");
    } catch (cause) { setMessage(describeApiError(cause)); }
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  async function choose(value: SessionSummary) {
    try {
      const history = await api.session(value.task_id);
      setSelected(history);
      setBranch(history.task.branch || `feature/${value.task_id.toLowerCase()}`);
      setMessage("");
    } catch (cause) { setMessage(describeApiError(cause)); }
  }
  async function continueRun() {
    if (!selected || !followUp.trim()) return;
    setBusy(true);
    try {
      await api.continueSession(selected.id, followUp.trim());
      setFollowUp(""); setSelected(await api.session(selected.id)); await load();
      setMessage("Follow-up queued from the persisted worktree.");
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function publish() {
    if (!selected || !branch.trim()) return;
    setBusy(true);
    try {
      const result = await api.publishTask(selected.id, branch.trim(), pullRequest);
      setMessage(`${result.approval_id} is awaiting scoped approval for ${result.actions.join(" and ")}.`);
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-medium text-teal-300">DURABLE RUNTIME</p><h1 className="mt-1 text-3xl font-semibold">Sessions</h1><p className="mt-2 text-sm text-slate-500">Resume persisted worktrees, publish approved changes, and connect external MCP clients.</p></div><button onClick={() => void load()} className="rounded-lg border border-white/[.08] p-2 text-slate-400" title="Refresh"><RefreshCw className="size-4" /></button></div>
    {message && <div className="mt-5 rounded-lg border border-blue-300/15 bg-blue-300/[.04] p-3 text-xs text-blue-200">{message}</div>}
    <div className="mt-6 grid gap-3 md:grid-cols-3"><Status label="Model" value={runtime?.active_model_provider || "Checking"} detail={runtime?.configured_model || ""} /><Status label="Sandbox" value={runtime?.sandbox_provider || "Checking"} detail={runtime?.sandbox_available ? "Ready" : "Unavailable"} /><Status label="MCP gateway" value={gateway?.auth_mode || "Checking"} detail={gateway?.streamable_http || ""} /></div>
    <div className="mt-6 grid gap-5 lg:grid-cols-[380px_1fr]">
      <section className="border-r border-white/[.07] pr-0 lg:pr-5"><div className="space-y-2">{sessions.map((value) => <button key={value.id} onClick={() => void choose(value)} className={`w-full border-l-2 px-4 py-3 text-left ${selected?.id === value.id ? "border-teal-300 bg-teal-300/[.04]" : "border-white/[.07] hover:bg-white/[.03]"}`}><div className="flex items-center justify-between gap-3"><span className="font-mono text-xs text-slate-300">{value.task_id}</span><span className="text-[10px] text-slate-500">{value.status}</span></div><p className="mt-2 text-sm">{value.title}</p><p className="mt-1 text-[10px] text-slate-600">{value.agent_id} · {value.workspace_persisted ? "workspace persisted" : "no workspace"}</p></button>)}{!sessions.length && <p className="p-8 text-center text-sm text-slate-600">No durable sessions yet.</p>}</div></section>
      {selected ? <section className="min-w-0"><div className="flex flex-wrap items-start justify-between gap-3"><div><span className="font-mono text-xs text-teal-300">{selected.id}</span><h2 className="mt-1 text-xl font-semibold">{selected.task.title}</h2><p className="mt-1 text-xs text-slate-500">{selected.task.status} · {selected.task.agent_id}</p></div><Link href={`/tasks/${selected.id}`} className="inline-flex items-center gap-2 rounded-lg border border-white/[.08] px-3 py-2 text-xs text-slate-300">Open workspace <ArrowUpRight className="size-3" /></Link></div>
        <div className="mt-5 grid gap-5 xl:grid-cols-2"><section className="border-t border-white/[.07] pt-4"><div className="flex items-center gap-2"><History className="size-4 text-teal-300" /><h3 className="text-sm font-medium">Continue session</h3></div><textarea value={followUp} onChange={(event) => setFollowUp(event.target.value)} disabled={!terminal.has(selected.task.status)} placeholder="Describe the follow-up change" className="mt-3 min-h-28 w-full border border-white/[.08] bg-black/20 p-3 text-sm outline-none focus:border-teal-300/40 disabled:opacity-40" /><button disabled={busy || !terminal.has(selected.task.status) || !followUp.trim()} onClick={() => void continueRun()} className="mt-2 inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Play className="size-4" />Continue</button></section>
          <section className="border-t border-white/[.07] pt-4"><div className="flex items-center gap-2"><GitPullRequest className="size-4 text-amber-300" /><h3 className="text-sm font-medium">Publish completed change</h3></div><input value={branch} onChange={(event) => setBranch(event.target.value)} className="mt-3 w-full border border-white/[.08] bg-black/20 px-3 py-2 font-mono text-xs outline-none focus:border-amber-300/40" /><label className="mt-3 flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={pullRequest} onChange={(event) => setPullRequest(event.target.checked)} />Create GitHub pull request</label><button disabled={busy || selected.task.status !== "DONE" || !branch.trim()} onClick={() => void publish()} className="mt-3 inline-flex items-center gap-2 border border-amber-300/20 px-4 py-2 text-sm text-amber-200 disabled:opacity-40"><Send className="size-4" />Request approval</button></section></div>
        <section className="mt-6 border-t border-white/[.07] pt-4"><div className="flex items-center gap-2"><Network className="size-4 text-blue-300" /><h3 className="text-sm font-medium">MCP transports</h3></div><div className="mt-3 space-y-2 font-mono text-[11px] text-slate-500"><p className="break-all">HTTP {gateway?.streamable_http}</p><p className="break-all">SSE {gateway?.sse}</p><p>Tools {gateway?.tools.join(", ")}</p></div></section>
      </section> : <div className="grid min-h-80 place-items-center text-sm text-slate-600">Select a session to inspect its durable state.</div>}
    </div>
  </div></Shell>;
}

function Status({ label, value, detail }: { label: string; value: string; detail: string }) { return <div className="border-t border-white/[.08] pt-3"><p className="text-[10px] uppercase text-slate-600">{label}</p><p className="mt-1 text-sm font-medium">{value}</p><p className="mt-1 truncate font-mono text-[10px] text-slate-600">{detail}</p></div>; }