"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, FileUp, LockKeyhole, Save } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { EvaluationDataset } from "@/lib/types";

type DatasetSource = {
  scenarios: Record<string, unknown>[];
};

export default function DatasetDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null);
  const [versions, setVersions] = useState<EvaluationDataset[]>([]);
  const [raw, setRaw] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [value, history] = await Promise.all([
        api.evaluationDataset(params.id), api.evaluationDatasetVersions(params.id),
      ]);
      setDataset(value); setVersions(history);
      setRaw(JSON.stringify({ scenarios: value.scenarios }, null, 2));
    } catch (cause) { setMessage(describeApiError(cause)); }
  }, [params.id]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  function parseSource(): DatasetSource {
    const source = JSON.parse(raw) as DatasetSource;
    if (!Array.isArray(source.scenarios)) throw new Error("Dataset JSON requires scenarios.");
    return source;
  }

  async function review() {
    if (!dataset || !reviewer.trim()) { setMessage("Enter the reviewer identity before marking this version reviewed."); return; }
    setBusy(true); setMessage("");
    try {
      const source = parseSource();
      const value = await api.reviewEvaluationDataset(dataset.id, source.scenarios, reviewer.trim());
      setDataset(value); await load(); setMessage(`Version ${value.version} is reviewed.`);
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  async function freeze() {
    if (!dataset || !reviewer.trim()) { setMessage("Enter the same reviewer identity used during review."); return; }
    setBusy(true); setMessage("");
    try { const value = await api.freezeEvaluationDataset(dataset.id, reviewer.trim()); setDataset(value); await load(); setMessage(`Version ${value.version} is frozen and immutable.`); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file || !dataset) return;
    setBusy(true); setMessage("");
    try {
      const source = JSON.parse(await file.text()) as DatasetSource;
      if (!Array.isArray(source.scenarios)) throw new Error("Uploaded JSON requires scenarios.");
      if (dataset.status === "FROZEN") {
        const created = await api.createEvaluationDatasetVersion(dataset.id, source.scenarios);
        router.push(`/datasets/${created.id}`);
      } else {
        setRaw(JSON.stringify(source, null, 2));
        setMessage("File loaded into the editor. Review the diff, enter a reviewer, and save this version.");
      }
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  if (!dataset) return <Shell><div className="grid min-h-[70vh] place-items-center text-sm text-slate-600">{message || "Loading dataset..."}</div></Shell>;
  const readOnly = dataset.status === "FROZEN";
  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <Link href="/datasets" className="inline-flex items-center gap-2 text-xs text-slate-500 hover:text-slate-200"><ArrowLeft className="size-4" />Datasets</Link>
    <header className="mt-5 flex flex-wrap items-start justify-between gap-4 border-b border-white/[.07] pb-6"><div><div className="flex items-center gap-3"><h1 className="text-2xl font-semibold">{dataset.dataset_name || dataset.agent_id}</h1><span className={statusTone(dataset.status)}>{dataset.status}</span></div><p className="mt-2 font-mono text-xs text-slate-600">{dataset.id} · version {dataset.version} · {dataset.content_hash?.slice(0, 16) || "unhashed"}</p></div><label className="inline-flex cursor-pointer items-center gap-2 border border-white/[.1] px-4 py-2 text-sm text-slate-300 hover:border-teal-300/30 hover:text-teal-200"><FileUp className="size-4" />Upload JSON<input type="file" accept="application/json,.json" onChange={(event) => void upload(event)} className="hidden" /></label></header>
    {message && <div className="mt-5 border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-200">{message}</div>}

    <div className="mt-6 grid gap-6 lg:grid-cols-[250px_1fr]">
      <aside className="border-r border-white/[.07] pr-5"><h2 className="text-[10px] font-semibold uppercase tracking-wider text-slate-600">Metadata</h2><dl className="mt-4 space-y-4 text-xs"><Meta label="Seed agent" value={dataset.agent_id} /><Meta label="Scenarios" value={String(dataset.scenarios.length)} /><Meta label="Generated by" value={dataset.generated_by} /><Meta label="Reviewer" value={dataset.reviewed_by || "Not reviewed"} /><Meta label="Updated" value={new Date(dataset.updated_at).toLocaleString()} /></dl><h2 className="mt-8 text-[10px] font-semibold uppercase tracking-wider text-slate-600">Version history</h2><div className="mt-3 space-y-1">{versions.map((item) => <Link key={item.id} href={`/datasets/${item.id}`} className={`flex items-center justify-between border-l-2 px-3 py-2 text-xs ${item.id === dataset.id ? "border-teal-300 bg-teal-300/[.04] text-slate-200" : "border-white/[.07] text-slate-500 hover:text-slate-300"}`}><span>Version {item.version}</span><span className={statusTone(item.status)}>{item.status}</span></Link>)}</div></aside>
      <section className="min-w-0"><div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="text-sm font-semibold">Dataset source</h2><p className="mt-1 text-xs text-slate-500">Scenarios are hashed as immutable evaluation input. Agent-specific adapter artifacts are generated when a run starts.</p></div><div className="flex flex-wrap items-center gap-2"><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="reviewer identity" className="border border-white/[.08] bg-black/20 px-3 py-2 text-xs" />{dataset.status !== "FROZEN" && <button disabled={busy || !reviewer.trim()} onClick={() => void review()} className="inline-flex items-center gap-2 border border-blue-300/20 px-3 py-2 text-xs text-blue-200 disabled:opacity-40"><Save className="size-4" />Save and mark reviewed</button>}<button disabled={busy || dataset.status !== "REVIEWED" || !reviewer.trim()} onClick={() => void freeze()} className="inline-flex items-center gap-2 border border-amber-300/20 px-3 py-2 text-xs text-amber-200 disabled:opacity-40"><LockKeyhole className="size-4" />Freeze</button></div></div><textarea spellCheck={false} readOnly={readOnly} value={raw} onChange={(event) => setRaw(event.target.value)} className="mt-4 min-h-[680px] w-full resize-y border border-white/[.08] bg-[#080c12] p-4 font-mono text-xs leading-5 text-slate-300 outline-none focus:border-teal-300/40 read-only:opacity-60" />{readOnly && <p className="mt-3 flex items-center gap-2 text-xs text-emerald-300"><Check className="size-4" />This version is immutable. Uploading a replacement creates a new draft version.</p>}</section>
    </div>
  </div></Shell>;
}

function Meta({ label, value }: { label: string; value: string }) { return <div><dt className="text-[10px] uppercase text-slate-600">{label}</dt><dd className="mt-1 break-words text-slate-300">{value}</dd></div>; }
function statusTone(status: string): string { return `text-[10px] font-semibold ${status === "FROZEN" ? "text-emerald-300" : status === "REVIEWED" ? "text-blue-300" : "text-amber-300"}`; }
