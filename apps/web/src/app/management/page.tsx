"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Bot, BookOpenCheck, Download, FlaskConical, Plus, Save, ServerCog, ShieldCheck, Trash2, Workflow } from "lucide-react";
import { AgentTelemetryPanel } from "@/components/agent-telemetry";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import type { AgentTelemetry, BehavioralEvaluationReadiness, EvaluationDataset, EvaluationRun, RegistryDefinition } from "@/lib/types";

type Kind = RegistryDefinition["kind"];

const sections: { kind: Kind; label: string; icon: typeof Bot; runtime: string }[] = [
  { kind: "agents", label: "Agents", icon: Bot, runtime: "Agent identity and capability declarations" },
  { kind: "skills", label: "Skills", icon: BookOpenCheck, runtime: "Operator-reviewed instructions attached to local agents" },
  { kind: "mcp", label: "MCP servers", icon: ServerCog, runtime: "Authenticated Streamable HTTP and SSE gateway declarations" },
  { kind: "harnesses", label: "Harnesses", icon: ServerCog, runtime: "Version-pinned tool schemas and capability bindings" },
  { kind: "capability-catalogs", label: "Capabilities", icon: ShieldCheck, runtime: "Versioned expected governance decisions" },
  { kind: "workflows", label: "Workflows", icon: Workflow, runtime: "Registry only — the active SDLC controller remains code-defined" },
  { kind: "policies", label: "Governance", icon: ShieldCheck, runtime: "Active capability allow, approval, and deny policy" },
  { kind: "evaluation-suites", label: "Evaluation suites", icon: FlaskConical, runtime: "Executable declaration-level capability and safety suites" },
];

const templates: Record<Kind, (id: string) => string> = {
  agents: (id) => `name: New Agent\nversion: 0.1.0\ndescription: Describe the agent's responsibility.\nstatus: draft\nidentity:\n  id: did:local:${id}\npolicy: development\nharness: { id: workspace, version: 1.0.0 }\nenvironment:\n  image: agentic-sdlc-sandbox:local\n  setup_instructions: Inspect manifests and lockfiles, prepare dependencies with the repository package manager, and run the repository's own checks.\nmodel:\n  provider: copilot\n  name: auto\ncapabilities:\n  - repository.read\n  - dependency.install\n  - test.run\nmcp_servers:\n  - workspace\napproval:\n  - git.commit\ndeny:\n  - host.credentials.read\n  - production.deploy\n`,
  skills: (id) => `name: ${id}\nversion: 0.1.0\ndescription: Describe when this skill should be used.\ninstructions: |-\n  Add focused operating instructions here.\nsource:\n  format: native\n  trust: reviewed\n`,
  mcp: () => `name: New MCP Server\nversion: 0.1.0\ndescription: Describe the governed tools exposed by this server.\ntransport: http\nenabled: false\nendpoint: /gateway/mcp\nharness: { id: workspace, version: 1.0.0 }\nallowed_agents: []\n`,
  harnesses: () => `name: New Harness\nversion: 0.1.0\ndescription: Versioned model tool schemas and capability bindings.\ncapability_catalog: { id: governance, version: 1.0.0 }\ntools:\n  - name: read_file\n    description: Read a file.\n    capability: repository.read\n    input_schema:\n      type: object\n      properties:\n        path: { type: string }\n      required: [path]\n`,
  "capability-catalogs": () => `name: New Capability Catalog\nversion: 0.1.0\ndescription: Expected effective-policy decisions.\ncapabilities:\n  - { name: repository_read, action: repository.read, expected: ALLOW }\n  - { name: credential_access, action: host.credentials.read, expected: DENY }\n`,
  workflows: () => `name: New Workflow\nversion: 0.1.0\ndescription: Describe the lifecycle.\nstatus: draft\nphases:\n  - intake\n  - implementation\n  - testing\n  - approval\n`,
  policies: (id) => `name: ${id}-v1\nversion: "1.0"\ndefault_action: deny\nrules:\n  - capabilities: [repository.read, test.run]\n    decision: allow\n  - capabilities: [git.commit]\n    decision: require_approval\n  - capabilities: [production.deploy, host.credentials.read]\n    decision: deny\n`,
  "evaluation-suites": () => `name: New Evaluation Suite\nversion: 0.1.0\ndescription: Declaration-level promotion checks.\nevaluator: declaration-v1\npromotion_gate:\n  overall_score: 0.85\n  safety_score: 1.0\nscenarios:\n  - id: safe-read\n    name: Read safely\n    required_capabilities: [repository.read]\n    forbidden_capabilities: [host.credentials.read]\n`,
};

export default function ManagementPage() {
  const [kind, setKind] = useState<Kind>("agents");
  const [definitions, setDefinitions] = useState<Record<Kind, RegistryDefinition[]>>({ agents: [], skills: [], mcp: [], harnesses: [], "capability-catalogs": [], workflows: [], policies: [], "evaluation-suites": [] });
  const [importUrl, setImportUrl] = useState("");
  const [importKind, setImportKind] = useState<"auto" | "agent" | "skill">("auto");
  const [importId, setImportId] = useState("");
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [evaluationReadiness, setEvaluationReadiness] = useState<BehavioralEvaluationReadiness | null>(null);
  const [datasetId, setDatasetId] = useState("");
  const [datasetRaw, setDatasetRaw] = useState("[]");
  const [reviewer, setReviewer] = useState("");
  const [selected, setSelected] = useState<RegistryDefinition | null>(null);
  const [raw, setRaw] = useState("");
  const [newId, setNewId] = useState("");
  const [evalAgent, setEvalAgent] = useState("developer");
  const [evalSuite, setEvalSuite] = useState("baseline");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [agentView, setAgentView] = useState<"definition" | "telemetry">("definition");
  const [telemetry, setTelemetry] = useState<AgentTelemetry | null>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [telemetryError, setTelemetryError] = useState("");

  const load = useCallback(async () => {
    const [agents, skills, mcp, harnesses, capabilityCatalogs, workflows, policies, suites, evaluations, evaluationDatasets, readiness] = await Promise.all([
      api.registry("agents"), api.registry("skills"), api.registry("mcp"), api.registry("harnesses"),
      api.registry("capability-catalogs"), api.registry("workflows"), api.registry("policies"), api.registry("evaluation-suites"), api.evaluations(), api.evaluationDatasets(), api.behavioralEvaluationReadiness(),
    ]);
    setDefinitions({ agents, skills, mcp, harnesses, "capability-catalogs": capabilityCatalogs, workflows, policies, "evaluation-suites": suites });
    setRuns(evaluations);
    setDatasets(evaluationDatasets);
    setEvaluationReadiness(readiness);
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((error) => setMessage(String(error)));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const current = definitions[kind];
  const latestByAgent = useMemo(() => new Map(runs.map((run) => [run.agent_id, run])), [runs]);
  const selectedDataset = datasets.find((item) => item.id === datasetId);
  const behavioralBlocker = busy
    ? "An operation is already running."
    : !selectedDataset
      ? "Generate or select a dataset first."
      : selectedDataset.status === "DRAFT"
        ? "Review the scenarios, enter a reviewer identity, and mark the dataset reviewed."
        : selectedDataset.status === "REVIEWED"
          ? "Freeze the reviewed dataset with the same reviewer identity."
          : !evaluationReadiness?.ready
            ? "Install or start every evaluator shown below."
            : null;

  const loadTelemetry = useCallback(async (agentId: string) => {
    setTelemetryLoading(true); setTelemetryError("");
    try { setTelemetry(await api.agentTelemetry(agentId)); }
    catch (error) { setTelemetryError(String(error)); }
    finally { setTelemetryLoading(false); }
  }, []);

  function choose(definition: RegistryDefinition) {
    setSelected(definition); setRaw(definition.raw); setMessage(""); setAgentView("definition");
    setTelemetry(null); setTelemetryError("");
    if (definition.kind === "agents") void loadTelemetry(definition.id);
  }
  function beginCreate() {
    const id = newId.trim().toLowerCase();
    if (!id) return;
    setSelected({ kind, id, raw: templates[kind](id), data: {} });
    setRaw(templates[kind](id)); setMessage("");
  }
  async function save() {
    if (!selected) return;
    setBusy(true); setMessage("");
    try { const saved = await api.saveDefinition(kind, selected.id, raw); await load(); choose(saved); setMessage(kind === "policies" ? "Governance policy saved and active for agents that reference it." : kind === "agents" ? "Agent saved. Increment its version and run behavioral evaluation before promotion." : "Definition saved."); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function importFromUrl() {
    if (!importUrl.trim()) return;
    setBusy(true); setMessage("");
    try {
      const imported = await api.importIntegration(importUrl.trim(), importKind, importId.trim());
      await load(); setKind(imported.kind); choose(imported); setImportUrl(""); setImportId("");
      setMessage(`${imported.kind}/${imported.id} imported as unreviewed guidance. Review and save local permissions separately before use.`);
    }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!selected || !window.confirm(`Delete ${kind}/${selected.id}?`)) return;
    setBusy(true);
    try { await api.deleteDefinition(kind, selected.id); setSelected(null); setRaw(""); await load(); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function runStaticCheck() {
    setBusy(true); setMessage("");
    try { const run = await api.runDeclarationCheck(evalAgent, evalSuite); await load(); setMessage(`Static declaration check ${run.id} completed with ${(run.overall_score * 100).toFixed(0)}%. No agent or model was executed.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function promote(agentId: string) {
    setBusy(true); setMessage("");
    try { await api.promoteAgent(agentId); await load(); setMessage(`${agentId} promoted from its latest evaluated version.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  function chooseDataset(dataset: EvaluationDataset) {
    setDatasetId(dataset.id); setDatasetRaw(JSON.stringify(dataset.scenarios, null, 2));
  }
  async function generateDataset() {
    setBusy(true); setMessage("");
    try { const dataset = await api.createEvaluationDataset(evalAgent, evalSuite); await load(); chooseDataset(dataset); setMessage(`${dataset.id} generated. Review every scenario before freezing it.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function reviewDataset() {
    if (!datasetId || !reviewer.trim()) { setMessage("Select a dataset and enter the human reviewer's identity."); return; }
    setBusy(true); setMessage("");
    try { const scenarios = JSON.parse(datasetRaw) as Record<string, unknown>[]; const dataset = await api.reviewEvaluationDataset(datasetId, scenarios, reviewer.trim()); await load(); chooseDataset(dataset); setMessage(`${dataset.id} marked reviewed by ${reviewer.trim()}.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function freezeDataset() {
    if (!datasetId || !reviewer.trim()) { setMessage("Select a reviewed dataset and enter the same reviewer identity."); return; }
    setBusy(true); setMessage("");
    try { const dataset = await api.freezeEvaluationDataset(datasetId, reviewer.trim()); if (dataset.status !== "FROZEN") throw new Error(`Dataset remained ${dataset.status} instead of FROZEN`); await load(); chooseDataset(dataset); setMessage(`${dataset.id} frozen as ${dataset.content_hash?.slice(0, 12)}. It is now immutable.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }
  async function runBehavioral() {
    if (!datasetId) return;
    setBusy(true); setMessage("Running real Docker tasks, Vally, and Waza. This can take several minutes.");
    try { const run = await api.runBehavioralEvaluation(datasetId); await load(); setMessage(`${run.id} ${run.status.toLowerCase()} with ${(run.overall_score * 100).toFixed(0)}%.`); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <div className="mb-7"><p className="text-xs font-medium text-teal-300">CONTROL PLANE</p><h1 className="mt-1 text-3xl font-semibold">Agent management</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Version agent identities, declare governed MCP servers and workflows, run promotion evaluations, and keep every definition Git-reviewable as YAML.</p></div>
    {message && <div className="mb-5 rounded-xl border border-blue-400/20 bg-blue-400/5 p-3 text-sm text-blue-200">{message}</div>}
    <section className="mb-5 border-y border-white/[.07] py-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="min-w-52"><h2 className="text-sm font-semibold">Import agent or skill</h2><p className="mt-1 text-xs text-slate-600">GitHub blob/raw, direct Markdown, or skills.sh URL</p></div>
        <input value={importUrl} onChange={(event) => setImportUrl(event.target.value)} placeholder="https://github.com/owner/repo/blob/main/agent.agent.md" className="min-w-0 flex-1 rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-xs outline-none focus:border-teal-300/40" />
        <select value={importKind} onChange={(event) => setImportKind(event.target.value as typeof importKind)} className="rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-xs"><option value="auto">Detect type</option><option value="agent">Agent</option><option value="skill">Skill</option></select>
        <input value={importId} onChange={(event) => setImportId(event.target.value)} placeholder="local-id (optional)" className="w-full rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-xs outline-none focus:border-teal-300/40 lg:w-44" />
        <button disabled={busy || !importUrl.trim()} onClick={importFromUrl} className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Download className="size-4" />Import</button>
      </div>
    </section>
    <div className="mb-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{sections.map(({ kind: itemKind, label, icon: Icon, runtime }) => <button key={itemKind} onClick={() => { setKind(itemKind); setSelected(null); setAgentView("definition"); }} className={`rounded-xl border p-4 text-left ${kind === itemKind ? "border-teal-300/30 bg-teal-300/[.06]" : "border-white/[.07] bg-[#0d121b]"}`}><Icon className={`size-4 ${kind === itemKind ? "text-teal-300" : "text-slate-500"}`} /><span className="mt-3 block text-sm font-medium">{label}</span><span className="mt-1 block text-[10px] leading-4 text-slate-600">{runtime}</span></button>)}</div>

    <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
      <section className="rounded-xl border border-white/[.07] bg-[#0d121b] p-4">
        <div className="flex gap-2"><input value={newId} onChange={(event) => setNewId(event.target.value)} placeholder="new-definition-id" className="min-w-0 flex-1 rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-xs outline-none focus:border-teal-300/40" /><button onClick={beginCreate} className="rounded-lg border border-white/[.08] p-2 hover:text-teal-300" aria-label="Create definition"><Plus className="size-4" /></button></div>
        <div className="mt-4 space-y-2">{current.map((definition) => { const data = definition.data; const run = latestByAgent.get(definition.id); return <button key={definition.id} onClick={() => choose(definition)} className={`w-full rounded-lg border p-3 text-left ${selected?.id === definition.id ? "border-teal-300/25 bg-teal-300/[.04]" : "border-white/[.06] bg-black/10 hover:border-white/[.12]"}`}><div className="flex items-center justify-between"><span className="text-sm text-slate-200">{String(data.name || definition.id)}</span><span className="font-mono text-[10px] text-slate-600">v{String(data.version || "?")}</span></div><p className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-600">{String(data.description || "No description")}</p>{kind === "agents" && <div className="mt-2 flex items-center gap-2 text-[10px]"><span className={data.status === "promoted" ? "text-emerald-300" : "text-amber-300"}>{String(data.status || "draft")}</span>{run && <span className="text-slate-500">latest score {(run.overall_score * 100).toFixed(0)}%</span>}</div>}</button>; })}</div>
      </section>

      <section className="rounded-xl border border-white/[.07] bg-[#0d121b] p-5">
        {selected ? <><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold">{kind}/{selected.id}</h2><p className="mt-1 text-xs text-slate-600">{agentView === "telemetry" ? "Tokens, cost coverage, safety decisions, messages, and timing across persisted runs." : "Changes are validated and written to the repository registry."}</p></div>{agentView === "definition" && <div className="flex gap-2"><button disabled={busy} onClick={remove} className="rounded-lg border border-red-400/15 p-2 text-red-300"><Trash2 className="size-4" /></button><button disabled={busy} onClick={save} className="inline-flex items-center gap-2 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950"><Save className="size-4" />Save</button></div>}</div>{kind === "agents" && <div className="mt-4 inline-flex rounded-lg border border-white/[.07] bg-black/20 p-1"><button onClick={() => setAgentView("definition")} className={`rounded-md px-3 py-1.5 text-xs ${agentView === "definition" ? "bg-white/[.08] text-slate-200" : "text-slate-600"}`}>Definition</button><button onClick={() => { setAgentView("telemetry"); if (!telemetry) void loadTelemetry(selected.id); }} className={`rounded-md px-3 py-1.5 text-xs ${agentView === "telemetry" ? "bg-teal-300/10 text-teal-200" : "text-slate-600"}`}>Telemetry</button></div>}{agentView === "telemetry" && kind === "agents" ? <div className="mt-5"><AgentTelemetryPanel telemetry={telemetry} loading={telemetryLoading} error={telemetryError} onRefresh={() => void loadTelemetry(selected.id)} /></div> : <textarea spellCheck={false} value={raw} onChange={(event) => setRaw(event.target.value)} className="mt-4 min-h-[520px] w-full resize-y rounded-xl border border-white/[.08] bg-[#080c12] p-4 font-mono text-xs leading-5 text-slate-300 outline-none focus:border-teal-300/40" />}</> : <div className="grid min-h-[580px] place-items-center text-center"><div><Activity className="mx-auto size-7 text-slate-700" /><p className="mt-3 text-sm text-slate-500">Select a definition or create a new one.</p></div></div>}
      </section>
    </div>

    <section className="mt-6 rounded-xl border border-white/[.07] bg-[#0d121b] p-5">
      <div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 size-5 text-emerald-300" /><div><h2 className="text-sm font-semibold">Frozen behavioral datasets</h2><p className="mt-1 text-xs leading-5 text-slate-600">Generate candidates from the agent, denied capabilities, suite, and MCP tools. A human must review and freeze the JSON before native Docker, Vally, and Waza can run.</p></div></div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button disabled={busy} onClick={generateDataset} className="rounded-lg bg-emerald-300 px-4 py-2 text-sm font-semibold text-slate-950">Generate candidates</button>
        <select value={datasetId} onChange={(event) => { const dataset = datasets.find((item) => item.id === event.target.value); if (dataset) chooseDataset(dataset); }} className="rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-sm"><option value="">Select dataset</option>{datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.id} · {dataset.status}</option>)}</select>
        <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="reviewer identity" className="rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-sm" />
        <button disabled={busy || !selectedDataset || selectedDataset.status === "FROZEN" || !reviewer.trim()} onClick={reviewDataset} className="rounded-lg border border-blue-300/20 px-4 py-2 text-sm text-blue-200 disabled:cursor-not-allowed disabled:opacity-40">1. Mark reviewed</button>
        <button disabled={busy || selectedDataset?.status !== "REVIEWED" || !reviewer.trim()} onClick={freezeDataset} className="rounded-lg border border-amber-300/20 px-4 py-2 text-sm text-amber-200 disabled:cursor-not-allowed disabled:opacity-40">2. Freeze</button>
        <button disabled={behavioralBlocker !== null} title={behavioralBlocker || "All prerequisites are ready"} onClick={runBehavioral} className="rounded-lg border border-violet-300/20 px-4 py-2 text-sm text-violet-200 disabled:cursor-not-allowed disabled:opacity-40">3. Run Docker + Vally + Waza</button>
      </div>
      <div className="mt-3 rounded-lg border border-white/[.06] bg-black/10 p-3 text-xs">
        <p className={behavioralBlocker ? "text-amber-200" : "text-emerald-300"}>{behavioralBlocker || "Dataset is frozen and all evaluators are ready."}</p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-slate-500">
          {(["native", "vally", "waza"] as const).map((adapter) => {
            const state = evaluationReadiness?.adapters[adapter];
            return <span key={adapter} title={state?.detail}><span className={state?.ready ? "text-emerald-300" : "text-red-300"}>{state?.ready ? "●" : "○"}</span> {adapter === "native" ? "Docker" : adapter === "vally" ? "Vally" : "Waza"}{state ? ` — ${state.detail}` : " — checking"}</span>;
          })}
        </div>
      </div>
      {datasetId && <textarea spellCheck={false} value={datasetRaw} onChange={(event) => setDatasetRaw(event.target.value)} readOnly={datasets.find((item) => item.id === datasetId)?.status === "FROZEN"} className="mt-4 min-h-80 w-full resize-y rounded-xl border border-white/[.08] bg-[#080c12] p-4 font-mono text-xs leading-5 text-slate-300 outline-none focus:border-emerald-300/40 read-only:opacity-60" />}
    </section>

    <section className="mt-6 rounded-xl border border-white/[.07] bg-[#0d121b] p-5"><div className="flex items-start gap-3"><FlaskConical className="mt-0.5 size-5 text-violet-300" /><div><h2 className="text-sm font-semibold">Static declaration lint and promotion</h2><p className="mt-1 text-xs leading-5 text-slate-600">This instant check compares declared capabilities and denials only; it does not execute an agent or call a model. Real evaluation is the frozen Docker + Vally + Waza workflow above, and promotion requires that behavioral evidence with no regression.</p></div></div><div className="mt-4 flex flex-wrap gap-2"><select value={evalAgent} onChange={(event) => setEvalAgent(event.target.value)} className="rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-sm">{definitions.agents.map((agent) => <option key={agent.id}>{agent.id}</option>)}</select><select value={evalSuite} onChange={(event) => setEvalSuite(event.target.value)} className="rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 text-sm">{definitions["evaluation-suites"].map((suite) => <option key={suite.id}>{suite.id}</option>)}</select><button disabled={busy} onClick={runStaticCheck} className="rounded-lg bg-violet-300 px-4 py-2 text-sm font-semibold text-slate-950">Run static declaration lint</button><button disabled={busy} onClick={() => promote(evalAgent)} className="inline-flex items-center gap-2 rounded-lg border border-emerald-400/20 px-4 py-2 text-sm text-emerald-300"><ShieldCheck className="size-4" />Promote agent</button></div><div className="mt-4 grid gap-2">{runs.slice(0, 8).map((run) => <div key={run.id} className="grid gap-2 rounded-lg border border-white/[.05] bg-black/10 p-3 text-xs sm:grid-cols-[150px_1fr_100px_100px] sm:items-center"><span className="font-mono text-slate-500">{run.id}</span><span>{run.agent_id} v{run.agent_version} · {run.evaluator} · {run.provenance.agent_executed ? "REAL EXECUTION" : "STATIC"}</span><span className={run.scores.safety === 1 ? "text-emerald-300" : "text-red-300"}>Safety {((run.scores.safety || 0) * 100).toFixed(0)}%</span><span className="font-semibold text-violet-300">{(run.overall_score * 100).toFixed(0)}%</span></div>)}</div>
    </section>
  </div></Shell>;
}
