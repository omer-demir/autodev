"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Archive, ArrowUpRight, FileCheck2 } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { EvidenceSummary } from "@/lib/types";

export default function EvidencePage() {
  const [items, setItems] = useState<EvidenceSummary[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setItems(await api.evidence()); setError(""); } catch (cause) { setError(describeApiError(cause)); } }, []);
  useEffect(() => { const initial = setTimeout(() => void load(), 0); return () => clearTimeout(initial); }, [load]);
  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8"><div className="mb-7"><p className="text-xs font-medium text-teal-300">CONTROL</p><h1 className="mt-1 text-3xl font-semibold">Evidence</h1><p className="mt-2 text-sm text-slate-500">Durable task, change, test, security, governance, and result records retained after containers are removed.</p></div>{error && <div className="mb-5 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{error}</div>}<div className="grid gap-4 md:grid-cols-2">{items.map((item) => <Link key={item.task_id} href={`/tasks/${item.task_id}`} className="group rounded-xl border border-white/[.07] bg-[#0d121b] p-5 hover:border-teal-300/20"><div className="flex items-start justify-between"><Archive className="size-5 text-teal-300" /><ArrowUpRight className="size-4 text-slate-700 group-hover:text-teal-300" /></div><p className="mt-4 font-mono text-xs text-slate-500">{item.task_id}</p><h2 className="mt-1 text-sm font-medium">{item.title}</h2><div className="mt-4 flex flex-wrap gap-1.5">{item.artifact_kinds.map((kind) => <span key={kind} className="rounded border border-white/[.06] bg-black/15 px-2 py-1 text-[10px] text-slate-500">{kind}</span>)}{!item.artifact_kinds.length && <span className="text-[10px] text-slate-700">No artifacts yet</span>}</div><div className="mt-4 flex items-center justify-between text-[10px]"><span className="text-slate-600">{new Date(item.updated_at).toLocaleString()}</span><span className="text-slate-400">{item.status}</span></div></Link>)}{!items.length && !error && <div className="col-span-full p-12 text-center"><FileCheck2 className="mx-auto size-6 text-slate-700" /><p className="mt-3 text-sm text-slate-600">No task evidence is available.</p></div>}</div></div></Shell>;
}
