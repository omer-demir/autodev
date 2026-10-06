"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Box, ExternalLink, HardDrive, Network, OctagonX } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { RuntimeStatus, Sandbox } from "@/lib/types";

export default function SandboxesPage() {
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => { try { const [values, status] = await Promise.all([api.sandboxes(), api.runtime()]); setSandboxes(values); setRuntime(status); setError(""); } catch (cause) { setError(describeApiError(cause)); } }, []);
  useEffect(() => { const initial = setTimeout(() => void load(), 0); const timer = setInterval(() => void load(), 5000); return () => { clearTimeout(initial); clearInterval(timer); }; }, [load]);
  async function kill(id: string) { setBusy(id); try { await api.killSandbox(id); await load(); } catch (cause) { setError(describeApiError(cause)); } finally { setBusy(""); } }
  const ready = sandboxes.filter((item) => item.status === "READY").length;
  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <div className="mb-7"><p className="text-xs font-medium text-teal-300">RUNTIME · {runtime?.sandbox_provider || "checking"}</p><h1 className="mt-1 text-3xl font-semibold">Sandboxes</h1><p className="mt-2 text-sm text-slate-500">Isolated execution boundaries, governed networks, persistent task worktrees, and session lifecycle controls.</p></div>
    {error && <div className="mb-5 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{error}</div>}
    <div className="mb-6 grid gap-3 sm:grid-cols-3"><Metric icon={Box} label="Ready sessions" value={ready} /><Metric icon={OctagonX} label="Disposed" value={sandboxes.length - ready} /><Metric icon={HardDrive} label="Persistent worktrees" value={sandboxes.filter((item) => item.host_workspace).length} /></div>
    <div className="grid gap-4">{sandboxes.map((sandbox) => <article key={sandbox.id} className="rounded-xl border border-white/[.07] bg-[#0d121b] p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className={`size-2 rounded-full ${sandbox.status === "READY" ? "bg-emerald-400" : "bg-slate-600"}`} /><h2 className="font-mono text-sm">{sandbox.id}</h2><span className="text-xs text-slate-600">{sandbox.provider}</span></div><Link href={`/tasks/${sandbox.task_id}`} className="mt-2 inline-flex items-center gap-1 text-xs text-teal-300 hover:underline">{sandbox.task_id}<ExternalLink className="size-3" /></Link></div><div className="flex items-center gap-2"><span className={`rounded-full border px-2 py-1 text-[10px] ${sandbox.status === "READY" ? "border-emerald-300/20 text-emerald-300" : "border-white/10 text-slate-500"}`}>{sandbox.status}</span>{sandbox.status === "READY" && <button disabled={busy === sandbox.id} onClick={() => void kill(sandbox.id)} className="rounded-lg border border-red-400/20 px-3 py-1.5 text-xs text-red-300 disabled:opacity-40">Kill container</button>}</div></div><div className="mt-5 grid gap-3 text-xs md:grid-cols-3"><Detail label="Container" value={sandbox.container_id?.slice(0, 12) || "Not allocated"} /><Detail label="Network" value={sandbox.network_policy} icon={Network} /><Detail label="Created" value={new Date(sandbox.created_at).toLocaleString()} /></div><div className="mt-3 rounded-lg bg-black/20 p-3 font-mono text-[10px] leading-5 text-slate-500"><p>container: {sandbox.workspace}</p><p className="break-all">host: {sandbox.host_workspace || "Unavailable"}</p></div></article>)}{!sandboxes.length && <div className="rounded-xl border border-white/[.07] p-12 text-center text-sm text-slate-600">No sandboxes have been created.</div>}</div>
  </div></Shell>;
}
function Metric({ icon: Icon, label, value }: { icon: typeof Box; label: string; value: number }) { return <div className="rounded-xl border border-white/[.07] bg-[#0d121b] p-5"><Icon className="size-4 text-teal-300" /><p className="mt-3 text-xs text-slate-600">{label}</p><p className="mt-1 font-mono text-3xl">{value}</p></div>; }
function Detail({ label, value, icon: Icon }: { label: string; value: string; icon?: typeof Box }) { return <div className="rounded-lg border border-white/[.05] bg-black/10 p-3"><p className="text-[10px] uppercase tracking-wider text-slate-700">{Icon && <Icon className="mr-1 inline size-3" />}{label}</p><p className="mt-1 font-mono text-slate-300">{value}</p></div>; }
