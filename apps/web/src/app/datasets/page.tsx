"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight, ChevronLeft, ChevronRight, Database, Plus, Search,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { EvaluationDatasetPage, RegistryDefinition } from "@/lib/types";

const emptyPage: EvaluationDatasetPage = { items: [], total: 0, page: 1, page_size: 20 };

export default function DatasetsPage() {
  const [result, setResult] = useState(emptyPage);
  const [agents, setAgents] = useState<RegistryDefinition[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [agent, setAgent] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [datasets, definitions] = await Promise.all([
        api.evaluationDatasetCatalog({ query, status, agent_id: agent, page, page_size: 20 }),
        api.registry("agents"),
      ]);
      setResult(datasets); setAgents(definitions); setMessage("");
    } catch (cause) { setMessage(describeApiError(cause)); }
  }, [agent, page, query, status]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);
  const pages = Math.max(1, Math.ceil(result.total / result.page_size));

  async function ensureBaselines() {
    setBusy(true); setMessage("");
    try {
      const datasets = await api.ensureEvaluationBaselines();
      await load();
      setMessage(`Role-specific dataset coverage is current for ${datasets.length} agents.`);
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-medium text-teal-300">EVALUATION ASSETS</p><h1 className="mt-1 text-3xl font-semibold">Datasets</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Versioned scenario, fixture, Vally, and Waza definitions used by behavioral evaluations. Frozen versions are immutable evidence inputs.</p></div>
      <button disabled={busy} onClick={() => void ensureBaselines()} className="inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Plus className="size-4" />Ensure role datasets</button>
    </header>
    {message && <div className="mt-5 border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-200">{message}</div>}

    <div className="mt-7 flex flex-wrap items-center gap-2 border-y border-white/[.07] py-4">
      <label className="relative min-w-64 flex-1"><Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-600" /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Search name, ID, or seed agent" className="w-full border border-white/[.08] bg-black/20 py-2 pl-9 pr-3 text-xs" /></label>
      <select aria-label="Filter by agent" value={agent} onChange={(event) => { setAgent(event.target.value); setPage(1); }} className="border border-white/[.08] bg-[#0d121b] px-3 py-2 text-xs text-slate-300"><option value="">All agents</option>{agents.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select>
      <select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }} className="border border-white/[.08] bg-[#0d121b] px-3 py-2 text-xs text-slate-300"><option value="">All states</option><option value="DRAFT">Draft</option><option value="REVIEWED">Reviewed</option><option value="FROZEN">Frozen</option></select>
    </div>

    <section className="mt-4 overflow-x-auto border border-white/[.07] bg-[#0d121b]">
      <div className="grid min-w-[760px] grid-cols-[1fr_80px_170px_110px_120px_28px] gap-3 border-b border-white/[.06] px-5 py-3 text-[10px] uppercase tracking-wider text-slate-600"><span>Dataset</span><span>Version</span><span>Seed agent</span><span>State</span><span>Updated</span><span /></div>
      {result.items.map((dataset) => <Link key={dataset.id} href={`/datasets/${dataset.id}`} className="grid min-w-[760px] grid-cols-[1fr_80px_170px_110px_120px_28px] gap-3 border-b border-white/[.05] px-5 py-4 text-xs last:border-0 hover:bg-white/[.025]"><span><b className="block font-medium text-slate-200">{dataset.dataset_name || dataset.agent_id}</b><span className="mt-1 block font-mono text-[10px] text-slate-600">{dataset.id}</span></span><span className="font-mono text-slate-300">v{dataset.version}</span><span className="text-slate-400">{dataset.agent_id}<small className="mt-1 block text-slate-600">initial source</small></span><span className={statusTone(dataset.status)}>{dataset.status}</span><span className="text-slate-500">{new Date(dataset.updated_at).toLocaleDateString()}</span><ArrowUpRight className="size-4 text-slate-600" /></Link>)}
      {!result.items.length && <div className="p-14 text-center"><Database className="mx-auto size-7 text-slate-700" /><p className="mt-3 text-sm text-slate-600">No datasets match these filters.</p></div>}
    </section>
    <div className="mt-4 flex items-center justify-between text-xs text-slate-500"><span>{result.total ? `${(page - 1) * result.page_size + 1}-${Math.min(page * result.page_size, result.total)} of ${result.total}` : "0 datasets"}</span><div className="flex items-center gap-2"><button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-white/[.08] p-2 disabled:opacity-30"><ChevronLeft className="size-4" /></button><span>Page {page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => setPage((value) => value + 1)} className="border border-white/[.08] p-2 disabled:opacity-30"><ChevronRight className="size-4" /></button></div></div>
  </div></Shell>;
}

function statusTone(status: string): string { return `text-[10px] font-semibold ${status === "FROZEN" ? "text-emerald-300" : status === "REVIEWED" ? "text-blue-300" : "text-amber-300"}`; }
