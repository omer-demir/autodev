"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight, CheckCircle2, CircleGauge, Clock3, Database,
  FlaskConical, GitCompareArrows, Play, ShieldCheck, XCircle,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type {
  BehavioralEvaluationReadiness, EvaluationDataset, EvaluationRun, RegistryDefinition,
} from "@/lib/types";

type JsonRecord = Record<string, unknown>;
type EvaluationTask = {
  task_id: string; scenario_id?: string; scenario_name?: string;
  dataset_id?: string; adapter?: string;
};

export default function EvaluationsPage() {
  const [agents, setAgents] = useState<RegistryDefinition[]>([]);
  const [suites, setSuites] = useState<RegistryDefinition[]>([]);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [readiness, setReadiness] = useState<BehavioralEvaluationReadiness | null>(null);
  const [agent, setAgent] = useState("developer");
  const [suite, setSuite] = useState("baseline");
  const [datasetId, setDatasetId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      const [agentValues, suiteValues, runValues, datasetValues, ready] = await Promise.all([
        api.registry("agents"), api.registry("evaluation-suites"), api.evaluations(),
        api.evaluationDatasets(), api.behavioralEvaluationReadiness(),
      ]);
      setAgents(agentValues); setSuites(suiteValues); setRuns(runValues);
      setDatasets(datasetValues); setReadiness(ready);
      setSelectedRunId((current) => current || runValues[0]?.id || "");
      setDatasetId((current) => current || datasetValues.find((item) => item.status === "FROZEN")?.id || "");
    } catch (cause) { setMessage(describeApiError(cause)); }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 5000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [load]);

  const frozen = useMemo(() => datasets.filter((item) => item.status === "FROZEN"), [datasets]);
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
    <header className="mb-7"><p className="text-xs font-medium text-teal-300">CONTROL</p><h1 className="mt-1 text-3xl font-semibold">Evaluations</h1><p className="mt-2 max-w-3xl text-sm text-slate-500">Inspect behavioral evidence from the aggregate score down to each adapter, scenario, and native task.</p></header>
    {message && <div className="mb-5 border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-200">{message}</div>}

    <div className="grid gap-3 sm:grid-cols-3">{(["native", "vally", "waza"] as const).map((name) => {
      const state = readiness?.adapters[name];
      return <div key={name} className="border-t border-white/[.08] pt-4">{state?.ready ? <CheckCircle2 className="size-5 text-emerald-300" /> : <XCircle className="size-5 text-red-300" />}<p className="mt-3 text-sm font-medium">{name === "native" ? "Native sandbox" : name === "vally" ? "Vally" : "Waza"}</p><p className="mt-1 text-[10px] leading-4 text-slate-600">{state?.detail || "Checking readiness"}</p></div>;
    })}</div>

    <section className="mt-7 border-y border-white/[.07] py-5"><div className="flex flex-wrap items-end gap-2"><label className="text-[10px] uppercase text-slate-600">Agent<select value={agent} onChange={(event) => setAgent(event.target.value)} className="mt-1 block border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200">{agents.map((item) => <option key={item.id}>{item.id}</option>)}</select></label><label className="text-[10px] uppercase text-slate-600">Suite<select value={suite} onChange={(event) => setSuite(event.target.value)} className="mt-1 block border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200">{suites.map((item) => <option key={item.id}>{item.id}</option>)}</select></label><button disabled={busy} onClick={() => void action(() => api.runDeclarationCheck(agent, suite), "Declaration evaluation completed.")} className="border border-violet-300/20 px-4 py-2 text-sm text-violet-200 disabled:opacity-40">Run declaration check</button><label className="min-w-64 flex-1 text-[10px] uppercase text-slate-600">Frozen dataset<select value={datasetId} onChange={(event) => setDatasetId(event.target.value)} className="mt-1 block w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm normal-case text-slate-200"><option value="">Select frozen dataset</option>{frozen.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.agent_id} · {item.scenarios.length} scenarios</option>)}</select></label><button disabled={busy || !datasetId || !readiness?.ready} onClick={() => void action(() => api.runBehavioralEvaluation(datasetId), "Behavioral evaluation started. Live task links appear below as scenarios begin.")} className="inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Play className="size-4" />Run behavioral evaluation</button></div><div className="mt-4 flex items-start gap-3 border-l border-blue-300/20 pl-3"><Database className="mt-0.5 size-4 shrink-0 text-blue-300" /><p className="text-xs leading-5 text-slate-500">A dataset is a frozen test specification, not a repository. The native adapter materializes one temporary Git fixture repository per scenario to exercise the production task pipeline. Vally and Waza translate the same scenarios into their own evaluator formats.</p></div></section>

    <div className="mt-7 grid gap-6 lg:grid-cols-[310px_1fr]">
      <section className="space-y-1 border-r border-white/[.07] pr-0 lg:pr-5"><h2 className="mb-3 text-xs font-semibold uppercase text-slate-500">Evaluation runs</h2>{runs.map((run) => <button key={run.id} onClick={() => setSelectedRunId(run.id)} className={`w-full border-l-2 px-3 py-3 text-left ${selectedRunId === run.id ? "border-teal-300 bg-teal-300/[.04]" : "border-white/[.07] hover:bg-white/[.03]"}`}><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs text-slate-300">{run.id}</span><span className={statusTone(run.status)}>{run.status}</span></div><p className="mt-2 text-xs text-slate-500">{run.agent_id} v{run.agent_version} · {run.evaluator}</p><p className="mt-1 font-mono text-lg">{percent(run.overall_score)}</p></button>)}{!runs.length && <p className="py-10 text-center text-sm text-slate-600">No evaluation runs yet.</p>}</section>
      {selectedRun ? <RunInspector run={selectedRun} /> : <div className="grid min-h-80 place-items-center text-sm text-slate-600">Select a run to inspect its evidence.</div>}
    </div>
  </div></Shell>;
}

function RunInspector({ run }: { run: EvaluationRun }) {
  const adapters = run.results.filter((item) => typeof item.adapter === "string");
  const tasks = evaluationTasks(run);
  const reasons = failureReasons(run);
  return <section className="min-w-0"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-3"><h2 className="font-mono text-lg">{run.id}</h2><span className={statusTone(run.status)}>{run.status}</span></div><p className="mt-2 text-xs text-slate-500">{run.agent_id} v{run.agent_version} · {run.suite_id} v{run.suite_version} · {run.evaluator}</p><p className="mt-1 text-[10px] text-slate-600">Dataset {run.dataset_id || "not applicable"} · {new Date(run.created_at).toLocaleString()}</p></div><div className="text-right"><p className="font-mono text-4xl">{percent(run.overall_score)}</p><p className="text-[10px] uppercase text-slate-600">overall score</p></div></div>

    {run.status === "FAILED" && <section className="mt-5 border-l-2 border-red-400 bg-red-400/[.04] p-4"><div className="flex items-center gap-2 text-sm font-medium text-red-200"><XCircle className="size-4" />Why this run failed</div><ul className="mt-3 space-y-1 text-xs leading-5 text-red-100/70">{reasons.map((reason) => <li key={reason}>• {reason}</li>)}</ul></section>}
    {run.status === "RUNNING" && <section className="mt-5 border-l-2 border-blue-300 bg-blue-300/[.04] p-4 text-xs text-blue-100/70"><Clock3 className="mr-2 inline size-4" />Evaluation is running. Native task links appear as each fixture starts; this view refreshes every five seconds.</section>}

    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="Overall" value={percent(run.overall_score)} icon={CircleGauge} />{Object.entries(run.scores).slice(0, 7).map(([name, value]) => <Metric key={name} label={name.replaceAll("_", " ")} value={value === null ? "N/A" : percent(value)} icon={name === "safety" ? ShieldCheck : FlaskConical} />)}</div>

    {tasks.length > 0 && <section className="mt-7"><h3 className="text-sm font-semibold">Native evaluation tasks</h3><div className="mt-3 grid gap-2 md:grid-cols-2">{tasks.map((task) => <Link key={task.task_id} href={`/tasks/${task.task_id}`} className="group border border-white/[.07] bg-black/10 p-3 hover:border-teal-300/30"><div className="flex items-center justify-between"><span className="font-mono text-xs text-teal-300">{task.task_id}</span><ArrowUpRight className="size-3 text-slate-600 group-hover:text-teal-300" /></div><p className="mt-2 text-xs text-slate-300">{task.scenario_name || task.scenario_id || "Evaluation scenario"}</p><p className="mt-1 text-[10px] text-slate-600">{task.adapter || "native"} · {task.dataset_id || run.dataset_id}</p></Link>)}</div></section>}

    <section className="mt-7"><h3 className="text-sm font-semibold">Run metrics</h3><div className="mt-3 grid gap-px bg-white/[.06] sm:grid-cols-3">{Object.entries(run.metrics || {}).map(([name, value]) => <div key={name} className="bg-[#0a0e15] p-4"><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-2 font-mono text-sm text-slate-300">{metricValue(value)}</p></div>)}{!Object.keys(run.metrics || {}).length && <p className="bg-[#0a0e15] p-4 text-xs text-slate-600">Metrics are recorded when execution completes.</p>}</div></section>

    <section className="mt-7"><h3 className="text-sm font-semibold">Adapter evidence</h3><div className="mt-3 space-y-3">{adapters.map((adapter, index) => <AdapterEvidence key={`${String(adapter.adapter)}-${index}`} adapter={adapter} />)}{!adapters.length && <p className="border border-white/[.07] p-5 text-xs text-slate-600">Adapter evidence has not been produced yet.</p>}</div></section>

    {Object.keys(run.comparison || {}).length > 0 && <section className="mt-7 border-t border-white/[.07] pt-5"><div className="flex items-center gap-2"><GitCompareArrows className="size-4 text-violet-300" /><h3 className="text-sm font-semibold">Baseline comparison</h3></div><div className="mt-3 grid gap-3 sm:grid-cols-4">{Object.entries(run.comparison || {}).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div></section>}
  </section>;
}

function AdapterEvidence({ adapter }: { adapter: JsonRecord }) {
  const scenarios = Array.isArray(adapter.results) ? adapter.results.filter(isRecord) : [];
  const passed = adapter.passed === true;
  return <article className="border border-white/[.07] bg-[#0d121b]"><header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[.06] px-4 py-3"><div className="flex items-center gap-2">{passed ? <CheckCircle2 className="size-4 text-emerald-300" /> : <XCircle className="size-4 text-red-300" />}<span className="text-sm font-medium capitalize">{String(adapter.adapter)}</span><span className="text-[10px] text-slate-600">{adapter.version ? `v${String(adapter.version)}` : ""}</span></div><div className="font-mono text-xs">{percent(numberValue(adapter.score))}</div></header>{adapter.error ? <p className="border-b border-red-300/10 bg-red-300/[.03] p-4 font-mono text-xs leading-5 text-red-200">{String(adapter.error)}</p> : null}<div className="grid gap-3 p-4 sm:grid-cols-3">{Object.entries(recordValue(adapter.metrics)).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div>{scenarios.length > 0 && <div className="divide-y divide-white/[.06] border-t border-white/[.06]">{scenarios.map((scenario, index) => <ScenarioEvidence key={String(scenario.id || index)} scenario={scenario} />)}</div>}</article>;
}

function ScenarioEvidence({ scenario }: { scenario: JsonRecord }) {
  const passed = scenario.passed === true;
  const dimensions = recordValue(scenario.dimensions);
  const metrics = recordValue(scenario.metrics);
  const judge = recordValue(scenario.judge);
  return <div className="p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2">{passed ? <CheckCircle2 className="size-4 text-emerald-300" /> : <XCircle className="size-4 text-red-300" />}<p className="text-sm font-medium">{String(scenario.name || scenario.id || "Scenario")}</p></div>{scenario.task_id ? <Link href={`/tasks/${String(scenario.task_id)}`} className="mt-2 inline-flex items-center gap-1 font-mono text-xs text-teal-300">{String(scenario.task_id)}<ArrowUpRight className="size-3" /></Link> : null}</div><p className="font-mono text-lg">{percent(numberValue(scenario.score))}</p></div><div className="mt-4 flex flex-wrap gap-2">{Object.entries(dimensions).map(([name, value]) => <span key={name} className={`border px-2 py-1 text-[10px] ${numberValue(value) >= 0.8 ? "border-emerald-300/20 text-emerald-300" : "border-red-300/20 text-red-300"}`}>{name} {percent(numberValue(value))}</span>)}</div><div className="mt-4 grid gap-3 sm:grid-cols-3">{Object.entries(metrics).map(([name, value]) => <div key={name}><p className="text-[10px] uppercase text-slate-600">{name.replaceAll("_", " ")}</p><p className="mt-1 font-mono text-xs text-slate-300">{metricValue(value)}</p></div>)}</div>{judge.reason ? <p className="mt-4 border-l border-white/[.1] pl-3 text-xs leading-5 text-slate-500">Judge: {String(judge.reason)}</p> : null}{scenario.cleanup_error ? <p className="mt-3 text-xs text-red-300">Cleanup: {String(scenario.cleanup_error)}</p> : null}{Array.isArray(scenario.missing_files) && scenario.missing_files.length > 0 ? <p className="mt-3 text-xs text-red-300">Missing files: {scenario.missing_files.map(String).join(", ")}</p> : null}</div>;
}

function Metric({ label, value, icon: Icon }: { label: string; value: string; icon: typeof CircleGauge }) { return <div className="border-t border-white/[.08] pt-3"><Icon className="size-4 text-teal-300" /><p className="mt-3 text-[10px] uppercase text-slate-600">{label}</p><p className="mt-1 font-mono text-xl">{value}</p></div>; }
function isRecord(value: unknown): value is JsonRecord { return typeof value === "object" && value !== null && !Array.isArray(value); }
function recordValue(value: unknown): JsonRecord { return isRecord(value) ? value : {}; }
function numberValue(value: unknown): number { return typeof value === "number" && Number.isFinite(value) ? value : 0; }
function percent(value: number): string { return `${(value * 100).toFixed(0)}%`; }
function metricValue(value: unknown): string { if (value === null || value === undefined) return "N/A"; if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3); if (typeof value === "boolean") return value ? "Yes" : "No"; return String(value); }
function statusTone(status: string): string { return `text-[10px] font-semibold ${status === "COMPLETED" ? "text-emerald-300" : status === "FAILED" ? "text-red-300" : "text-blue-300"}`; }

function evaluationTasks(run: EvaluationRun): EvaluationTask[] {
  const values = Array.isArray(run.provenance.tasks) ? run.provenance.tasks.filter(isRecord) : [];
  const tasks = values.map((item) => ({ task_id: String(item.task_id), scenario_id: item.scenario_id ? String(item.scenario_id) : undefined, scenario_name: item.scenario_name ? String(item.scenario_name) : undefined, dataset_id: item.dataset_id ? String(item.dataset_id) : undefined, adapter: item.adapter ? String(item.adapter) : undefined }));
  for (const adapter of run.results) {
    if (!Array.isArray(adapter.results)) continue;
    for (const scenario of adapter.results.filter(isRecord)) {
      if (!scenario.task_id || tasks.some((item) => item.task_id === String(scenario.task_id))) continue;
      tasks.push({ task_id: String(scenario.task_id), scenario_id: scenario.id ? String(scenario.id) : undefined, scenario_name: scenario.name ? String(scenario.name) : undefined, dataset_id: run.dataset_id || undefined, adapter: String(adapter.adapter || "native") });
    }
  }
  return tasks;
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