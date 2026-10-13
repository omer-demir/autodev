"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, BrainCircuit, CheckCircle2, CircleGauge, Clock3, Database,
  FileText, FlaskConical, GitCompareArrows, Play, ShieldCheck, Terminal,
  Wrench, XCircle,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type {
  BehavioralEvaluationReadiness, EvaluationArtifact, EvaluationDataset,
  EvaluationEvent, EvaluationModelCatalog, EvaluationRun, RegistryDefinition,
} from "@/lib/types";

type JsonRecord = Record<string, unknown>;

export default function EvaluationsPage() {
  const [agents, setAgents] = useState<RegistryDefinition[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [readiness, setReadiness] = useState<BehavioralEvaluationReadiness | null>(null);
  const [agentId, setAgentId] = useState("");
  const [datasetId, setDatasetId] = useState("");
  const [modelProvider, setModelProvider] = useState<"copilot" | "ollama">("ollama");
  const [modelName, setModelName] = useState("");
  const [modelCatalog, setModelCatalog] = useState<EvaluationModelCatalog | null>(null);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState("");
  const [verboseLogging, setVerboseLogging] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [agentValues, runValues, datasetValues, ready] = await Promise.all([
        api.registry("agents"), api.evaluations(), api.evaluationDatasets(),
        api.behavioralEvaluationReadiness(),
      ]);
      setAgents(agentValues); setRuns(runValues); setDatasets(datasetValues); setReadiness(ready);
      setAgentId((current) => current || agentValues[0]?.id || "");
      setSelectedRunId((current) => current || runValues[0]?.id || "");
      setDatasetId((current) => current || datasetValues.find((item) => item.status === "FROZEN")?.id || "");
    } catch (cause) { setMessage(describeApiError(cause)); }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 5000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [load]);

  useEffect(() => {
    let active = true;
    void api.evaluationModels(modelProvider).then((catalog) => {
      if (!active) return;
      setModelCatalog(catalog);
      const names = catalog.models.map((item) => item.name || item.id || "").filter(Boolean);
      setModelName((current) => names.includes(current) ? current : (catalog.default_model && names.includes(catalog.default_model) ? catalog.default_model : names[0] || ""));
    }).catch((cause) => {
      if (!active) return;
      setModelName("");
      setModelsError(describeApiError(cause));
    }).finally(() => { if (active) setModelsLoading(false); });
    return () => { active = false; };
  }, [modelProvider]);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === datasetId) || null,
    [datasetId, datasets],
  );
  const selectedRun = runs.find((run) => run.id === selectedRunId) || null;

  async function action(work: () => Promise<EvaluationRun>, success: string) {
    setBusy(true); setMessage("");
    try {
      const run = await work();
      setSelectedRunId(run.id);
      await load();
      setMessage(success);
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <header className="mb-7"><p className="text-xs font-medium text-teal-300">CONTROL</p><h1 className="mt-1 text-3xl font-semibold">Evaluations</h1><p className="mt-2 max-w-3xl text-sm text-slate-500">Inspect evaluation-owned behavioral evidence from the aggregate score down to each adapter and scenario.</p></header>
    {message && <div className="mb-5 border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-200">{message}</div>}

    <div className="grid gap-3 sm:grid-cols-3">{(["native", "vally", "waza"] as const).map((name) => {
      const state = readiness?.adapters[name];
      return <div key={name} className="border-t border-white/[.08] pt-4">{state?.ready ? <CheckCircle2 className="size-5 text-emerald-300" /> : <XCircle className="size-5 text-red-300" />}<p className="mt-3 text-sm font-medium">{name === "native" ? "Native sandbox" : name === "vally" ? "Vally" : "Waza"}</p><p className="mt-1 text-[10px] leading-4 text-slate-600">{state?.detail || "Checking readiness"}</p></div>;
    })}</div>

    <section className="mt-7 border-y border-white/[.07] py-5">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-sm font-semibold">Run an evaluation</h2><p className="mt-1 text-xs leading-5 text-slate-500">Choose an agent and a dataset independently. The dataset supplies scenarios; the current agent definition supplies behavior and tools.</p></div>
        <Link href="/datasets" className="inline-flex items-center gap-2 border border-teal-300/20 px-4 py-2 text-sm text-teal-200"><Database className="size-4" />Manage datasets</Link>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-52 text-[10px] uppercase text-slate-600">Agent<select value={agentId} onChange={(event) => setAgentId(event.target.value)} className="mt-1 block w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200"><option value="">Select agent</option>{agents.map((item) => <option key={item.id} value={item.id}>{item.id} · v{String(item.data.version || "unknown")}</option>)}</select></label>
        <label className="min-w-80 flex-1 text-[10px] uppercase text-slate-600">Dataset<select value={datasetId} onChange={(event) => setDatasetId(event.target.value)} className="mt-1 block w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200"><option value="">Select dataset</option>{datasets.map((item) => <option key={item.id} value={item.id}>{item.dataset_name || item.agent_id} · v{item.version} · {item.status}</option>)}</select></label>
        <button disabled={busy || !agentId || !selectedDataset} onClick={() => selectedDataset && void action(() => api.runDeclarationCheck(agentId, selectedDataset.id), "Declaration evaluation completed.")} className="border border-violet-300/20 px-4 py-2 text-sm text-violet-200 disabled:opacity-40">Run declaration check</button>
        <label className="text-[10px] uppercase text-slate-600">Provider<select value={modelProvider} onChange={(event) => { setModelProvider(event.target.value as "copilot" | "ollama"); setModelName(""); setModelCatalog(null); setModelsError(""); setModelsLoading(true); }} className="mt-1 block border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200"><option value="ollama">Ollama</option><option value="copilot">GitHub Copilot</option></select></label>
        <label className="text-[10px] uppercase text-slate-600">Evaluator model<select value={modelName} disabled={modelsLoading || Boolean(modelsError) || !modelCatalog?.models.length} onChange={(event) => setModelName(event.target.value)} className="mt-1 block w-52 border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200 disabled:opacity-40"><option value="">{modelsLoading ? "Loading models…" : modelsError ? "Models unavailable" : "Select a model"}</option>{modelCatalog?.models.map((item) => <option key={item.name || item.id} value={item.name || item.id}>{item.name || item.id}{item.automatic ? " (automatic)" : ""}</option>)}</select></label>
        <label className="flex items-center gap-2 border border-white/[.08] px-3 py-2 text-xs text-slate-400"><input type="checkbox" checked={verboseLogging} onChange={(event) => setVerboseLogging(event.target.checked)} className="accent-teal-300" />Verbose LLM trace</label>
        <button disabled={busy || modelsLoading || Boolean(modelsError) || !agentId || selectedDataset?.status !== "FROZEN" || !modelName || !readiness?.ready} onClick={() => selectedDataset && void action(() => api.runBehavioralEvaluation(agentId, datasetId, modelProvider, modelName, verboseLogging), "Behavioral evaluation started in its isolated evaluation workspace.")} className="inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Play className="size-4" />Run behavioral evaluation</button>
      </div>
      {selectedDataset && selectedDataset.status !== "FROZEN" && <p className="mt-3 border-l-2 border-amber-300/40 pl-3 text-xs leading-5 text-amber-100/70">Declaration checks are available now. Review and freeze this dataset before running behavioral evaluation.</p>}
      {modelsError && <p className="mt-3 border-l-2 border-red-300/40 pl-3 text-xs leading-5 text-red-200">{modelsError}</p>}
      {verboseLogging && <p className="mt-3 border-l-2 border-amber-300/40 pl-3 text-xs leading-5 text-amber-100/70">Verbose traces persist exact model prompts and responses. They can contain source code and sensitive repository context; enable them only when evaluation evidence retention is appropriate.</p>}
      <div className="mt-4 flex items-start gap-3 border-l border-blue-300/20 pl-3"><Database className="mt-0.5 size-4 shrink-0 text-blue-300" /><p className="text-xs leading-5 text-slate-500">Behavioral runs use isolated evaluation workspaces and do not create product tasks or sessions. Promotion requires a human-reviewed frozen dataset.</p></div>
    </section>

    <div className="mt-7 grid gap-6 lg:grid-cols-[310px_1fr]">
      <section className="space-y-1 border-r border-white/[.07] pr-0 lg:pr-5"><h2 className="mb-3 text-xs font-semibold uppercase text-slate-500">Evaluation runs</h2>{runs.map((run) => <button key={run.id} onClick={() => setSelectedRunId(run.id)} className={`w-full border-l-2 px-3 py-3 text-left ${selectedRunId === run.id ? "border-teal-300 bg-teal-300/[.04]" : "border-white/[.07] hover:bg-white/[.03]"}`}><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs text-slate-300">{run.id}</span><span className={statusTone(run.status)}>{run.status}</span></div><p className="mt-2 text-xs text-slate-500">{run.agent_id} v{run.agent_version} · {run.evaluator}</p><p className="mt-1 font-mono text-lg">{percent(run.overall_score)}</p></button>)}{!runs.length && <p className="py-10 text-center text-sm text-slate-600">No evaluation runs yet.</p>}</section>
      {selectedRun ? <RunInspector run={selectedRun} /> : <div className="grid min-h-80 place-items-center text-sm text-slate-600">Select a run to inspect its evidence.</div>}
    </div>
  </div></Shell>;
}

function RunInspector({ run }: { run: EvaluationRun }) {
  const [fetchedDetail, setFetchedDetail] = useState<EvaluationRun | null>(null);
  const [events, setEvents] = useState<EvaluationEvent[]>([]);
  const [artifacts, setArtifacts] = useState<EvaluationArtifact[]>([]);
  const [tab, setTab] = useState("overview");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const detail = fetchedDetail?.id === run.id ? fetchedDetail : run;

  useEffect(() => {
    let active = true;
    async function loadDetail() {
      try {
        const [nextRun, nextEvents, nextArtifacts] = await Promise.all([
          api.evaluation(run.id), api.evaluationEvents(run.id), api.evaluationArtifacts(run.id),
        ]);
        if (!active) return;
        setFetchedDetail(nextRun); setEvents(nextEvents); setArtifacts(nextArtifacts.files);
      } catch { /* The page-level refresh reports API availability. */ }
    }
    void loadDetail();
    const timer = window.setInterval(() => void loadDetail(), detail.status === "RUNNING" ? 2000 : 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [run.id, detail.status]);

  const adapters = detail.results.filter((item) => typeof item.adapter === "string");
  const reasons = failureReasons(detail);
  const modelCalls = traceRows(adapters, "model_calls");
  const toolCalls = traceRows(adapters, "tool_calls");
  const progress = numberValue(detail.metrics?.progress_percent);
  const tabs = [
    ["overview", "Overview", CircleGauge], ["timeline", "Live timeline", Activity],
    ["models", `Model calls (${modelCalls.length})`, BrainCircuit],
    ["tools", `Tools (${toolCalls.length})`, Wrench],
    ["logs", "Logs", Terminal], ["artifacts", `Artifacts (${artifacts.length})`, FileText],
  ] as const;

  async function cancelRun() {
    setCancelBusy(true);
    setCancelError("");
    try {
      const cancelled = await api.cancelEvaluation(detail.id);
      setFetchedDetail(cancelled);
      setEvents(await api.evaluationEvents(detail.id));
    } catch (cause) {
      setCancelError(describeApiError(cause));
    } finally {
      setCancelBusy(false);
    }
  }

  return <section className="min-w-0"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-3"><h2 className="font-mono text-lg">{detail.id}</h2><span className={statusTone(detail.status)}>{detail.status}</span></div><p className="mt-2 text-xs text-slate-500">{detail.agent_id} v{detail.agent_version} · {detail.evaluator}</p><p className="mt-1 text-[10px] text-slate-600">Dataset {detail.dataset_id || "not applicable"} · {new Date(detail.created_at).toLocaleString()}</p></div><div className="flex items-start gap-3">{detail.status === "RUNNING" && <button disabled={cancelBusy} onClick={() => void cancelRun()} className="inline-flex items-center gap-2 border border-red-300/30 px-3 py-2 text-xs text-red-200 disabled:opacity-40"><XCircle className="size-4" />{cancelBusy ? "Cancelling…" : "Cancel run"}</button>}<div className="text-right"><p className="font-mono text-4xl">{percent(detail.overall_score)}</p><p className="text-[10px] uppercase text-slate-600">overall score</p></div></div></div>

    {cancelError && <section className="mt-5 border-l-2 border-red-400 bg-red-400/[.04] p-4 text-xs text-red-200">{cancelError}</section>}
    {detail.status === "FAILED" && <section className="mt-5 border-l-2 border-red-400 bg-red-400/[.04] p-4"><div className="flex items-center gap-2 text-sm font-medium text-red-200"><XCircle className="size-4" />Why this run failed</div><ul className="mt-3 space-y-1 text-xs leading-5 text-red-100/70">{reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></section>}
    {detail.status === "CANCELLED" && <section className="mt-5 border-l-2 border-amber-300 bg-amber-300/[.04] p-4 text-xs text-amber-100/70">This run was cancelled. Partial metrics, events, logs, and artifacts produced before cancellation remain available.</section>}
    {detail.status === "RUNNING" && <section className="mt-5 border-l-2 border-blue-300 bg-blue-300/[.04] p-4"><div className="flex items-center justify-between gap-3 text-xs text-blue-100/70"><span><Clock3 className="mr-2 inline size-4" />{String(detail.metrics?.phase || "running")} · {String(detail.metrics?.current_adapter || "orchestrator")}{detail.metrics?.current_scenario ? ` · ${String(detail.metrics.current_scenario)}` : ""}</span><span className="font-mono">{numberValue(detail.metrics?.progress_completed)}/{numberValue(detail.metrics?.progress_total)}</span></div><div className="mt-3 h-1.5 bg-white/[.06]"><div className="h-full bg-blue-300 transition-all" style={{ width: `${Math.max(2, progress * 100)}%` }} /></div></section>}

    <nav className="mt-6 flex gap-1 overflow-x-auto border-b border-white/[.07]">{tabs.map(([id, label, Icon]) => <button key={id} onClick={() => setTab(id)} className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-xs ${tab === id ? "border-teal-300 text-teal-200" : "border-transparent text-slate-500 hover:text-slate-300"}`}><Icon className="size-3.5" />{label}</button>)}</nav>

    {tab === "overview" && <>
      <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Overall" value={percent(detail.overall_score)} icon={CircleGauge} />{Object.entries(detail.scores).slice(0, 7).map(([name, value]) => <Metric key={name} label={name.replaceAll("_", " ")} value={value === null ? "N/A" : percent(value)} icon={name === "safety" ? ShieldCheck : FlaskConical} />)}</div>
      <section className="mt-7"><h3 className="text-sm font-semibold">Run metrics</h3><div className="mt-3 grid gap-px bg-white/[.06] sm:grid-cols-3">{Object.entries(detail.metrics || {}).map(([name, value]) => <div key={name} className="bg-[#0a0e15] p-4"><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-2 font-mono text-sm text-slate-300">{metricValue(value)}</p></div>)}{!Object.keys(detail.metrics || {}).length && <p className="bg-[#0a0e15] p-4 text-xs text-slate-600">Metrics appear as execution progresses.</p>}</div></section>
      <section className="mt-7"><h3 className="text-sm font-semibold">Adapter evidence</h3><div className="mt-3 space-y-3">{adapters.map((adapter, index) => <AdapterEvidence key={`${String(adapter.adapter)}-${index}`} adapter={adapter} />)}{!adapters.length && <p className="border border-white/[.07] p-5 text-xs text-slate-600">Adapter evidence has not been produced yet.</p>}</div></section>
      {Object.keys(detail.comparison || {}).length > 0 && <section className="mt-7 border-t border-white/[.07] pt-5"><div className="flex items-center gap-2"><GitCompareArrows className="size-4 text-violet-300" /><h3 className="text-sm font-semibold">Baseline comparison</h3></div><div className="mt-3 grid gap-3 sm:grid-cols-4">{Object.entries(detail.comparison || {}).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div></section>}
      <section className="mt-7 border-t border-white/[.07] pt-5"><h3 className="text-sm font-semibold">Run configuration</h3><div className="mt-3 grid gap-3 sm:grid-cols-3">{Object.entries(detail.provenance || {}).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 break-words font-mono text-xs text-slate-300">{typeof value === "object" ? JSON.stringify(value) : metricValue(value)}</p></div>)}</div></section>
    </>}

    {tab === "timeline" && <Timeline events={events} />}
    {tab === "models" && <TraceTable rows={modelCalls} kind="model" />}
    {tab === "tools" && <TraceTable rows={toolCalls} kind="tool" />}
    {tab === "logs" && <LogViewer adapters={adapters} events={events} />}
    {tab === "artifacts" && <ArtifactViewer artifacts={artifacts} />}
  </section>;
}

function AdapterEvidence({ adapter }: { adapter: JsonRecord }) {
  const scenarios = Array.isArray(adapter.results) ? adapter.results.filter(isRecord) : [];
  const passed = adapter.passed === true;
  const running = adapter.status === "RUNNING";
  return <article className="border border-white/[.07] bg-[#0d121b]"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.06] px-4 py-3"><div className="flex items-center gap-2">{running ? <Clock3 className="size-4 animate-pulse text-blue-300" /> : passed ? <CheckCircle2 className="size-4 text-emerald-300" /> : <XCircle className="size-4 text-red-300" />}<span className="text-sm font-medium capitalize">{String(adapter.adapter)}</span><span className="text-[10px] text-slate-600">{adapter.version ? `v${String(adapter.version)}` : String(adapter.status || "")}</span></div><div className="font-mono text-xs">{percent(numberValue(adapter.score))}</div></header>{adapter.error ? <p className="border-b border-red-300/10 bg-red-300/[.03] p-4 font-mono text-xs leading-5 text-red-200">{String(adapter.error)}</p> : null}<div className="grid gap-3 p-4 sm:grid-cols-3">{Object.entries(recordValue(adapter.metrics)).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div>{scenarios.length > 0 && <div className="divide-y divide-white/[.06] border-t border-white/[.06]">{scenarios.map((scenario, index) => <ScenarioEvidence key={String(scenario.id || scenario.scenario_id || index)} scenario={scenario} />)}</div>}</article>;
}

function ScenarioEvidence({ scenario }: { scenario: JsonRecord }) {
  const passed = scenario.passed === true;
  const dimensions = recordValue(scenario.dimensions);
  const metrics = recordValue(scenario.metrics);
  const judge = recordValue(scenario.judge);
  const tests = recordValue(scenario.tests);
  const changes = recordValue(scenario.changes);
  return <div className="p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2">{passed ? <CheckCircle2 className="size-4 text-emerald-300" /> : <XCircle className="size-4 text-red-300" />}<p className="text-sm font-medium">{String(scenario.name || scenario.id || scenario.scenario_id || "Scenario")}</p></div>{scenario.execution_id ? <p className="mt-2 font-mono text-xs text-teal-300">{String(scenario.execution_id)}</p> : null}</div><p className="font-mono text-lg">{percent(numberValue(scenario.score))}</p></div><div className="mt-4 flex flex-wrap gap-2">{Object.entries(dimensions).map(([name, value]) => <span key={name} className={`border px-2 py-1 text-[10px] ${numberValue(value) >= 0.8 ? "border-emerald-300/20 text-emerald-300" : "border-red-300/20 text-red-300"}`}>{name} {percent(numberValue(value))}</span>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-3">{Object.entries(metrics).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div>{judge.reason ? <p className="mt-4 border-l border-white/[.1] pl-3 text-xs leading-5 text-slate-500">Judge: {String(judge.reason)}</p> : null}{scenario.cleanup_error ? <p className="mt-3 text-xs text-red-300">Cleanup: {String(scenario.cleanup_error)}</p> : null}{Array.isArray(scenario.missing_files) && scenario.missing_files.length > 0 ? <p className="mt-3 text-xs text-red-300">Missing files: {scenario.missing_files.map(String).join(", ")}</p> : null}{(scenario.summary || tests.output || changes.diff) ? <details className="mt-4 border-t border-white/[.06] pt-3"><summary className="cursor-pointer text-xs text-teal-300">Execution output, tests, and diff</summary>{scenario.summary ? <EvidenceBlock label="Agent summary" value={String(scenario.summary)} /> : null}{tests.output ? <EvidenceBlock label={`Test output · exit ${metricValue(tests.exit_code)}`} value={String(tests.output)} /> : null}{changes.diff ? <EvidenceBlock label="Repository diff" value={String(changes.diff)} /> : null}</details> : null}</div>;
}

function Timeline({ events }: { events: EvaluationEvent[] }) {
  return <section className="mt-5"><div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">Persistent event stream</h3><span className="text-[10px] text-slate-600">{events.length} events · live refresh</span></div><div className="max-h-[720px] space-y-px overflow-auto border border-white/[.06] bg-black/20">{events.map((event) => <article key={event.id} className="grid gap-2 border-b border-white/[.05] p-3 sm:grid-cols-[90px_150px_1fr]"><time className="font-mono text-[10px] text-slate-600">{new Date(event.created_at).toLocaleTimeString()}</time><div><p className={`text-[10px] font-semibold ${event.severity === "error" ? "text-red-300" : event.severity === "warning" ? "text-amber-300" : "text-teal-300"}`}>{event.type}</p><p className="mt-1 text-[10px] text-slate-600">{[event.adapter, event.scenario_id].filter(Boolean).join(" · ")}</p></div><div><p className="text-xs text-slate-300">{event.title}</p>{event.detail && <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-slate-500">{event.detail}</pre>}</div></article>)}{!events.length && <p className="p-6 text-center text-xs text-slate-600">Waiting for evaluation events.</p>}</div></section>;
}

function TraceTable({ rows, kind }: { rows: JsonRecord[]; kind: "model" | "tool" }) {
  return <section className="mt-5 overflow-x-auto"><table className="w-full min-w-[720px] text-left text-xs"><thead className="border-b border-white/[.08] text-[10px] uppercase text-slate-600"><tr><th className="p-3">#</th><th className="p-3">{kind === "model" ? "Provider / model" : "Tool / capability"}</th><th className="p-3">Latency</th><th className="p-3">{kind === "model" ? "Input" : "Status"}</th><th className="p-3">{kind === "model" ? "Output" : "Evidence"}</th></tr></thead><tbody className="divide-y divide-white/[.05]">{rows.map((row, index) => <tr key={`${String(row.scenario_id)}-${index}`}><td className="p-3 font-mono text-slate-600">{metricValue(row.sequence || index + 1)}</td><td className="p-3"><p className="text-slate-300">{kind === "model" ? `${metricValue(row.provider)} / ${metricValue(row.model)}` : metricValue(row.name)}</p><p className="mt-1 text-[10px] text-slate-600">{metricValue(row.scenario_id)}{kind === "tool" && row.capability ? ` · ${metricValue(row.capability)}` : ""}</p></td><td className="p-3 font-mono text-slate-400">{row.latency_ms == null ? "N/A" : `${metricValue(row.latency_ms)} ms`}</td><td className="p-3 font-mono text-slate-400">{kind === "model" ? metricValue(row.input_tokens) : metricValue(row.status)}</td><td className="max-w-sm p-3 font-mono text-slate-400">{kind === "model" ? metricValue(row.output_tokens) : <details><summary className="cursor-pointer text-teal-300">Inspect</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-[10px]">{`${metricValue(row.arguments)}\n\n${metricValue(row.result)}`}</pre></details>}</td></tr>)}</tbody></table>{!rows.length && <p className="border border-white/[.06] p-6 text-center text-xs text-slate-600">No {kind} calls have been recorded.</p>}</section>;
}

function LogViewer({ adapters, events }: { adapters: JsonRecord[]; events: EvaluationEvent[] }) {
  const logs = adapters.filter((adapter) => typeof adapter.log_excerpt === "string" && adapter.log_excerpt);
  const verbose = events.filter((event) => ["model.prompt", "model.response", "model.error"].includes(event.type));
  return <section className="mt-5 space-y-4">{verbose.length > 0 && <div className="border-l-2 border-amber-300/40 bg-amber-300/[.03] p-3 text-xs text-amber-100/70">This run contains persisted model prompts or responses. Treat this evidence as sensitive.</div>}{logs.map((adapter) => <EvidenceBlock key={String(adapter.adapter)} label={`${String(adapter.adapter)} console.log`} value={String(adapter.log_excerpt)} />)}{verbose.map((event) => <EvidenceBlock key={event.id} label={`${event.type} · ${event.scenario_id || "run"}`} value={event.detail} />)}{!logs.length && !verbose.length && <p className="border border-white/[.06] p-6 text-center text-xs text-slate-600">No console or verbose model logs are available yet.</p>}</section>;
}

function ArtifactViewer({ artifacts }: { artifacts: EvaluationArtifact[] }) {
  return <section className="mt-5 space-y-2">{artifacts.map((artifact) => <details key={artifact.path} className="border border-white/[.06] bg-black/20"><summary className="flex cursor-pointer items-center justify-between gap-3 p-3 text-xs"><span className="font-mono text-teal-300">{artifact.path}</span><span className="text-slate-600">{formatBytes(artifact.size_bytes)}</span></summary>{artifact.preview !== null && <pre className="max-h-96 overflow-auto border-t border-white/[.05] p-4 whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-slate-400">{artifact.preview}</pre>}</details>)}{!artifacts.length && <p className="border border-white/[.06] p-6 text-center text-xs text-slate-600">No adapter artifacts have been written yet.</p>}</section>;
}

function EvidenceBlock({ label, value }: { label: string; value: string }) { return <div className="mt-3"><p className="mb-2 text-[10px] uppercase text-slate-600">{label}</p><pre className="max-h-80 overflow-auto border border-white/[.06] bg-black/30 p-3 whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-slate-400">{value}</pre></div>; }

function Metric({ label, value, icon: Icon }: { label: string; value: string; icon: typeof CircleGauge }) { return <div className="border-t border-white/[.08] pt-3"><Icon className="size-4 text-teal-300" /><p className="mt-3 text-[10px] uppercase text-slate-600">{label}</p><p className="mt-1 font-mono text-xl">{value}</p></div>; }
function isRecord(value: unknown): value is JsonRecord { return typeof value === "object" && value !== null && !Array.isArray(value); }
function recordValue(value: unknown): JsonRecord { return isRecord(value) ? value : {}; }
function numberValue(value: unknown): number { return typeof value === "number" && Number.isFinite(value) ? value : 0; }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%`; }
function metricValue(value: unknown): string { if (value === null || value === undefined) return "N/A"; if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3); if (typeof value === "boolean") return value ? "Yes" : "No"; return String(value); }
function statusTone(status: string): string { return `text-[10px] font-semibold ${status === "COMPLETED" ? "text-emerald-300" : status === "FAILED" ? "text-red-300" : status === "CANCELLED" ? "text-amber-300" : "text-blue-300"}`; }
function formatBytes(value: number): string { if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
function traceRows(adapters: JsonRecord[], key: "model_calls" | "tool_calls"): JsonRecord[] {
  const rows: JsonRecord[] = [];
  for (const adapter of adapters) {
    if (!Array.isArray(adapter.results)) continue;
    for (const scenario of adapter.results.filter(isRecord)) {
      const values = scenario[key];
      if (!Array.isArray(values)) continue;
      for (const value of values.filter(isRecord)) rows.push({
        ...value,
        adapter: adapter.adapter,
        scenario_id: scenario.id || scenario.scenario_id,
      });
    }
  }
  return rows;
}

function failureReasons(run: EvaluationRun): string[] {
  const reasons: string[] = [];
  for (const adapter of run.results) {
    const name = String(adapter.adapter || "orchestrator");
    if (adapter.error) reasons.push(`${name}: ${String(adapter.error)}`);
    if (adapter.passed === false && !adapter.error) reasons.push(`${name} did not meet its pass threshold (${percent(numberValue(adapter.score))}).`);
    if (!Array.isArray(adapter.results)) continue;
    for (const scenario of adapter.results.filter(isRecord)) {
      if (scenario.passed === true) continue;
      const label = String(scenario.name || scenario.id || "scenario");
      const missingTerms = Array.isArray(scenario.missing_output_terms) ? scenario.missing_output_terms.map(String) : [];
      if (missingTerms.length) reasons.push(`${label}: missing required output terms: ${missingTerms.join(", ")}.`);
      const judge = recordValue(scenario.judge);
      if (judge.reason) reasons.push(`${label}: ${String(judge.reason)}.`);
      const failedDimensions = Object.entries(recordValue(scenario.dimensions)).filter(([, value]) => numberValue(value) < 0.8).map(([key]) => key);
      if (failedDimensions.length) reasons.push(`${label}: failed ${failedDimensions.join(", ")} metrics.`);
      if (scenario.cleanup_error) reasons.push(`${label}: sandbox cleanup failed: ${String(scenario.cleanup_error)}`);
    }
  }
  if (!reasons.length) reasons.push("The run did not satisfy every selected adapter, but no structured failure reason was recorded.");
  return [...new Set(reasons)];
}