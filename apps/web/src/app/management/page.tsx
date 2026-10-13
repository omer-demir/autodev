"use client";

import Link from "next/link";
import { DragEvent, useCallback, useEffect, useState } from "react";
import {
  Activity, Bot, BookOpenCheck, CheckCircle2, Download,
  Network, Plus, Save, ServerCog, ShieldCheck, Trash2, Workflow,
} from "lucide-react";
import { AgentTelemetryPanel } from "@/components/agent-telemetry";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { AgentTelemetry, AuthUser, RegistryDefinition } from "@/lib/types";

type Kind = RegistryDefinition["kind"];
type DefinitionMap = Record<Kind, RegistryDefinition[]>;

const sections: { kind: Kind; label: string; icon: typeof Bot; runtime: string }[] = [
  { kind: "agents", label: "Agents", icon: Bot, runtime: "Identity, tools, evaluation, and promotion" },
  { kind: "skills", label: "Skills", icon: BookOpenCheck, runtime: "Reusable reviewed operating instructions" },
  { kind: "mcp", label: "MCP servers", icon: ServerCog, runtime: "Transport definitions and connection checks" },
  { kind: "harnesses", label: "Harnesses", icon: ServerCog, runtime: "Versioned tool schemas and capability bindings" },
  { kind: "capability-catalogs", label: "Capabilities", icon: ShieldCheck, runtime: "Supported runtime actions and expected decisions" },
  { kind: "workflows", label: "Workflows", icon: Workflow, runtime: "Validated DAG stages, artifacts, and handoffs" },
  { kind: "policies", label: "Governance", icon: ShieldCheck, runtime: "Supported actions mapped to policy decisions" },
];

const templates: Record<Kind, (id: string) => string> = {
  agents: (id) => `name: New Agent\nversion: 0.1.0\ndescription: Describe the agent's responsibility.\nstatus: draft\nevaluation_required: true\nidentity:\n  id: did:local:${id}\npolicy: development\nharness: { id: workspace, version: 1.0.0 }\ncapabilities: [repository.read, test.run]\napproval: [git.commit]\ndeny: [host.credentials.read, production.deploy]\n`,
  skills: (id) => `name: ${id}\nversion: 0.1.0\ndescription: Describe when this skill should be used.\ninstructions: |-\n  Add focused operating instructions here.\nsource: { format: native, trust: reviewed }\n`,
  mcp: () => `name: New MCP Server\nversion: 0.1.0\ndescription: Governed tools exposed by this server.\ntransport: http\nenabled: false\nendpoint: https://example.invalid/mcp\nallowed_agents: []\n`,
  harnesses: () => `name: New Harness\nversion: 0.1.0\ndescription: Versioned tool schemas and capability bindings.\ncapability_catalog: { id: governance, version: 1.0.0 }\ntools:\n  - name: read_file\n    description: Read a file.\n    capability: repository.read\n    input_schema: { type: object, properties: { path: { type: string } }, required: [path] }\n`,
  "capability-catalogs": () => `name: New Capability Catalog\nversion: 0.1.0\ndescription: Expected effective-policy decisions.\ncapabilities:\n  - { name: repository_read, action: repository.read, expected: ALLOW }\n`,
  workflows: () => `name: New Workflow\nversion: 0.1.0\ndescription: Governed multi-agent outcome.\nstatus: draft\nphases:\n  - { id: planning, status: PLANNING, label: Planning, progress: 15 }\n  - { id: done, status: DONE, label: Done, progress: 100 }\norchestration: { mode: dag, max_parallel: 2 }\nstages:\n  - id: research\n    agent: did:local:researcher\n    responsibility: Gather grounded repository context.\n    inputs: [request, workspace]\n    outputs: [research-brief]\n`,
  policies: (id) => `name: ${id}-v1\nversion: "1.0"\ndefault_action: deny\nrules:\n  - capabilities: [repository.read, test.run]\n    decision: allow\n  - capabilities: [git.commit]\n    decision: require_approval\n`,
  "evaluation-suites": () => `name: New Evaluation Suite\nversion: 0.1.0\ndescription: Reusable scenarios and pass thresholds for agent versions.\nevaluator: declaration-v1\npromotion_gate: { overall_score: 0.85, safety_score: 1.0 }\nscenarios:\n  - id: safe-read\n    name: Read safely\n    required_capabilities: [repository.read]\n    forbidden_capabilities: [host.credentials.read]\n`,
};

const emptyDefinitions: DefinitionMap = { agents: [], skills: [], mcp: [], harnesses: [], "capability-catalogs": [], workflows: [], policies: [], "evaluation-suites": [] };

export default function ManagementPage() {
  const [kind, setKind] = useState<Kind>("agents");
  const [definitions, setDefinitions] = useState<DefinitionMap>(emptyDefinitions);
  const [selected, setSelected] = useState<RegistryDefinition | null>(null);
  const [raw, setRaw] = useState("");
  const [newId, setNewId] = useState("");
  const [importUrl, setImportUrl] = useState("");
  const [importKind, setImportKind] = useState<"auto" | "agent" | "skill">("auto");
  const [importId, setImportId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [agentView, setAgentView] = useState<"definition" | "telemetry">("definition");
  const [telemetry, setTelemetry] = useState<AgentTelemetry | null>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [supportedCapabilities, setSupportedCapabilities] = useState<string[]>([]);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  const load = useCallback(async () => {
    const values = await Promise.all(sections.map((section) => api.registry(section.kind)));
    const next = { ...emptyDefinitions };
    sections.forEach((section, index) => { next[section.kind] = values[index]; });
    setDefinitions(next);
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void Promise.all([
    load(),
    api.runtimeCapabilities().then((value) => setSupportedCapabilities(value.capabilities)),
    api.me().then(setCurrentUser),
  ]).catch((cause) => setMessage(describeApiError(cause))), 0); return () => window.clearTimeout(timer); }, [load]);

  async function loadTelemetry(agentId: string) {
    setTelemetryLoading(true);
    try { setTelemetry(await api.agentTelemetry(agentId)); } catch { setTelemetry(null); } finally { setTelemetryLoading(false); }
  }
  function choose(definition: RegistryDefinition) {
    setSelected(definition); setRaw(definition.raw); setMessage(""); setAgentView("definition"); setTelemetry(null);
    if (definition.kind === "agents") {
      void loadTelemetry(definition.id);
    }
  }
  function beginCreate() {
    const id = newId.trim().toLowerCase(); if (!id) return;
    const draft: RegistryDefinition = { kind, id, raw: templates[kind](id), data: {} };
    setSelected(draft); setRaw(draft.raw); setMessage("");
  }
  async function save() {
    if (!selected) return; setBusy(true); setMessage("");
    try { const value = await api.saveDefinition(kind, selected.id, raw); await load(); choose(value); setMessage(`${kind}/${value.id} saved and validated.`); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function remove() {
    if (!selected || !window.confirm(`Delete ${kind}/${selected.id}?`)) return; setBusy(true);
    try { await api.deleteDefinition(kind, selected.id); setSelected(null); setRaw(""); await load(); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function importDefinition() {
    if (!importUrl.trim()) return; setBusy(true); setMessage("");
    try { const value = await api.importIntegration(importUrl.trim(), importKind, importId.trim()); await load(); setKind(value.kind); choose(value); setMessage(`${value.kind}/${value.id} imported as unreviewed guidance.`); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function check() {
    if (!selected) return; setBusy(true); setMessage("");
    try { const value = await api.checkDefinition(selected.kind, selected.id); setMessage(value.detail); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function promote() {
    if (!selected) return; setBusy(true); setMessage("");
    try { await api.promoteAgent(selected.id); await load(); setMessage(`${selected.id} promoted from verified behavioral evidence.`); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function setEvaluationRequirement(evaluationRequired: boolean) {
    if (!selected) return;
    const action = evaluationRequired ? "restore evaluation requirements" : "allow execution without evaluation";
    const reason = window.prompt(`Reason to ${action} for ${selected.id}:`);
    if (!reason?.trim()) return;
    setBusy(true); setMessage("");
    try {
      const value = await api.setAgentEvaluationRequirement(selected.id, evaluationRequired, reason.trim());
      await load(); choose(value);
      setMessage(evaluationRequired
        ? `${selected.id} requires promotion evidence again.`
        : `${selected.id} may run without evaluation; normal governance still applies.`);
    } catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function assignStage(stageId: string, agentId: string) {
    if (!selected) return; setBusy(true); setMessage("");
    try { const value = await api.assignWorkflowStageAgent(selected.id, stageId, agentId); await load(); choose(value); setMessage(`${agentId} assigned to ${stageId}. Workflow validation passed.`); }
    catch (cause) { setMessage(describeApiError(cause)); } finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <header><p className="text-xs font-medium text-teal-300">CONTROL PLANE</p><h1 className="mt-1 text-3xl font-semibold">Agents & tools</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Manage each registry through its own validation and operational lifecycle. Definitions remain Git-reviewable YAML.</p></header>
    {message && <div className="mt-5 border border-blue-400/20 bg-blue-400/5 p-4 text-sm text-blue-200">{message}</div>}
    <section className="mt-6 border-y border-white/[.07] py-4"><div className="flex flex-col gap-3 lg:flex-row lg:items-center"><div className="min-w-52"><h2 className="text-sm font-semibold">Import agent or skill</h2><p className="mt-1 text-xs text-slate-600">GitHub, direct Markdown, or skills.sh</p></div><input value={importUrl} onChange={(event) => setImportUrl(event.target.value)} placeholder="https://github.com/owner/repo/blob/main/agent.agent.md" className="min-w-0 flex-1 border border-white/[.08] bg-black/20 px-3 py-2 text-xs" /><select value={importKind} onChange={(event) => setImportKind(event.target.value as typeof importKind)} className="border border-white/[.08] bg-black/20 px-3 py-2 text-xs"><option value="auto">Detect type</option><option value="agent">Agent</option><option value="skill">Skill</option></select><input value={importId} onChange={(event) => setImportId(event.target.value)} placeholder="local-id" className="w-40 border border-white/[.08] bg-black/20 px-3 py-2 text-xs" /><button disabled={busy || !importUrl.trim()} onClick={() => void importDefinition()} className="inline-flex items-center justify-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Download className="size-4" />Import</button></div></section>
    <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{sections.map(({ kind: value, label, icon: Icon, runtime }) => <button key={value} onClick={() => { setKind(value); setSelected(null); }} className={`border p-4 text-left ${kind === value ? "border-teal-300/30 bg-teal-300/[.06]" : "border-white/[.07] bg-[#0d121b]"}`}><Icon className={`size-4 ${kind === value ? "text-teal-300" : "text-slate-500"}`} /><span className="mt-3 block text-sm font-medium">{label}</span><span className="mt-1 block text-[10px] leading-4 text-slate-600">{runtime}</span></button>)}</div>

    <div className="mt-5 grid gap-5 lg:grid-cols-[320px_1fr]">
      <section className="border border-white/[.07] bg-[#0d121b] p-4"><div className="flex gap-2"><input value={newId} onChange={(event) => setNewId(event.target.value)} placeholder="new-definition-id" className="min-w-0 flex-1 border border-white/[.08] bg-black/20 px-3 py-2 text-xs" /><button onClick={beginCreate} className="border border-white/[.08] p-2" aria-label="Create definition"><Plus className="size-4" /></button></div><div className="mt-4 space-y-1">{definitions[kind].map((definition) => <button key={definition.id} onClick={() => choose(definition)} className={`w-full border-l-2 px-3 py-3 text-left ${selected?.id === definition.id ? "border-teal-300 bg-teal-300/[.04]" : "border-white/[.07] hover:bg-white/[.025]"}`}><span className="block text-sm text-slate-200">{String(definition.data.name || definition.id)}</span><span className="mt-1 block font-mono text-[10px] text-slate-600">{definition.id} · v{String(definition.data.version || "?")}</span></button>)}</div></section>
      <section className="min-w-0 border border-white/[.07] bg-[#0d121b] p-5">{selected ? <><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-semibold">{kind}/{selected.id}</h2><p className="mt-1 text-xs text-slate-600">Save invokes the authoritative backend validator for this definition type.</p></div>{agentView === "definition" && <div className="flex gap-2"><button disabled={busy} onClick={() => void remove()} className="border border-red-400/15 p-2 text-red-300"><Trash2 className="size-4" /></button><button disabled={busy} onClick={() => void save()} className="inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950"><Save className="size-4" />Save</button></div>}</div>{kind === "agents" && <div className="mt-4 inline-flex border border-white/[.07] bg-black/20 p-1"><button onClick={() => setAgentView("definition")} className={`px-3 py-1.5 text-xs ${agentView === "definition" ? "bg-white/[.08] text-slate-200" : "text-slate-600"}`}>Definition</button><button onClick={() => setAgentView("telemetry")} className={`px-3 py-1.5 text-xs ${agentView === "telemetry" ? "bg-teal-300/10 text-teal-200" : "text-slate-600"}`}>Telemetry</button></div>}{agentView === "telemetry" && kind === "agents" ? <div className="mt-5"><AgentTelemetryPanel telemetry={telemetry} loading={telemetryLoading} error="" onRefresh={() => void loadTelemetry(selected.id)} /></div> : <textarea spellCheck={false} value={raw} onChange={(event) => setRaw(event.target.value)} className="mt-4 min-h-[520px] w-full resize-y border border-white/[.08] bg-[#080c12] p-4 font-mono text-xs leading-5 text-slate-300 outline-none focus:border-teal-300/40" />}</> : <div className="grid min-h-[580px] place-items-center text-center"><div><Activity className="mx-auto size-7 text-slate-700" /><p className="mt-3 text-sm text-slate-600">Select a {kind.replaceAll("-", " ")} definition.</p></div></div>}</section>
    </div>
    {selected && <DefinitionActions definition={selected} agents={definitions.agents} supportedCapabilities={supportedCapabilities} busy={busy} isAdmin={currentUser?.role === "admin"} onCheck={check} onPromote={promote} onSetEvaluationRequirement={setEvaluationRequirement} onAssignStage={assignStage} />}
  </div></Shell>;
}

function DefinitionActions({ definition, agents, supportedCapabilities, busy, isAdmin, onCheck, onPromote, onSetEvaluationRequirement, onAssignStage }: { definition: RegistryDefinition; agents: RegistryDefinition[]; supportedCapabilities: string[]; busy: boolean; isAdmin: boolean; onCheck: () => Promise<void>; onPromote: () => Promise<void>; onSetEvaluationRequirement: (evaluationRequired: boolean) => Promise<void>; onAssignStage: (stageId: string, agentId: string) => Promise<void> }) {
  const kind = definition.kind;
  const stages = Array.isArray(definition.data.stages) ? definition.data.stages.filter(isRecord) : [];
  const drop = (event: DragEvent<HTMLDivElement>, stageId: string) => { event.preventDefault(); const agentId = event.dataTransfer.getData("text/agent-id"); if (agentId) void onAssignStage(stageId, agentId); };
  return <section className="mt-6 border-y border-white/[.07] py-5"><div className="flex items-start gap-3"><CheckCircle2 className="mt-0.5 size-5 text-teal-300" /><div><h2 className="text-sm font-semibold">{actionTitle(kind)}</h2><p className="mt-1 text-xs leading-5 text-slate-500">{actionDescription(kind)}</p></div></div>
    {kind === "agents" && <div className="mt-4 flex flex-wrap gap-2"><Link href="/datasets" className="border border-teal-300/20 px-4 py-2 text-sm text-teal-200">Manage datasets</Link><Link href="/evaluations" className="border border-blue-300/20 px-4 py-2 text-sm text-blue-200">Run evaluations</Link><button disabled={busy} onClick={() => void onPromote()} className="inline-flex items-center gap-2 border border-emerald-300/20 px-4 py-2 text-sm text-emerald-300"><ShieldCheck className="size-4" />Promote agent</button>{isAdmin && <button disabled={busy} onClick={() => void onSetEvaluationRequirement(definition.data.evaluation_required === false)} className="border border-amber-300/20 px-4 py-2 text-sm text-amber-200">{definition.data.evaluation_required === false ? "Require evaluation" : "Allow without evaluation"}</button>}</div>}
    {kind === "agents" && definition.data.evaluation_required === false && <p className="mt-3 border-l-2 border-amber-300/30 pl-3 text-xs leading-5 text-amber-200">Evaluation bypass approved by {String((definition.data.evaluation_override as Record<string, unknown> | undefined)?.approved_by || "repository administrator")}. The agent remains subject to identity, policy, sandbox, capability, and approval controls.</p>}
    {kind !== "agents" && kind !== "harnesses" && kind !== "workflows" && <button disabled={busy} onClick={() => void onCheck()} className="mt-4 border border-teal-300/20 px-4 py-2 text-sm text-teal-200">{kind === "mcp" ? "Test connection" : "Run static check"}</button>}
    {kind === "harnesses" && <p className="mt-4 border-l border-white/[.1] pl-3 text-xs leading-5 text-slate-500">Harnesses are declarative tool contracts. Save validates tool schemas, capability bindings, and resolver names; there is no promotion lifecycle.</p>}
    {(kind === "capability-catalogs" || kind === "policies") && <div className="mt-4 border border-white/[.07] bg-black/15 p-4"><p className="text-xs font-medium text-slate-300">Accepted runtime actions</p><p className="mt-1 text-[10px] leading-4 text-slate-600">This list comes from the control plane resolver. Save rejects any other action.</p><div className="mt-3 flex flex-wrap gap-1.5">{supportedCapabilities.map((capability) => <span key={capability} className="border border-teal-300/10 bg-teal-300/[.03] px-2 py-1 font-mono text-[10px] text-teal-200">{capability}</span>)}</div></div>}
    {kind === "workflows" && <div className="mt-5"><div className="flex flex-wrap gap-2">{agents.map((agent) => <button key={agent.id} draggable onDragStart={(event) => event.dataTransfer.setData("text/agent-id", agent.id)} className="cursor-grab border border-white/[.08] px-3 py-2 text-xs text-slate-400 active:cursor-grabbing"><Bot className="mr-2 inline size-3" />{agent.id}</button>)}</div><div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{stages.map((stage) => <div key={String(stage.id)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(event, String(stage.id))} className="border border-white/[.08] bg-black/15 p-4 hover:border-teal-300/30"><div className="flex items-center gap-2"><Network className="size-4 text-violet-300" /><b className="text-sm">{String(stage.id)}</b></div><p className="mt-3 text-xs text-teal-200">{String(stage.agent || "Unassigned").replace("did:local:", "")}</p><p className="mt-2 text-[10px] leading-4 text-slate-600">Depends on: {Array.isArray(stage.depends_on) && stage.depends_on.length ? stage.depends_on.map(String).join(", ") : "start"}</p></div>)}</div><button disabled={busy} onClick={() => void onCheck()} className="mt-4 border border-teal-300/20 px-4 py-2 text-sm text-teal-200">Validate workflow DAG</button></div>}
  </section>;
}

function actionTitle(kind: Kind): string { return ({ agents: "Agent evaluation and promotion", skills: "Skill validation", mcp: "MCP connection", harnesses: "Harness contract", "capability-catalogs": "Capability validation", workflows: "Workflow topology", policies: "Governance validation", "evaluation-suites": "Evaluation suite validation" })[kind]; }
function actionDescription(kind: Kind): string { return ({ agents: "Agents use declaration checks, versioned behavioral datasets, adapter runs, and promotion gates.", skills: "Native validation checks required metadata and instruction structure. Waza or Claude skill checking is reported only when such an integration is configured.", mcp: "Built-in routes are verified against the local gateway; external HTTP endpoints receive a live reachability probe.", harnesses: "Harnesses pin model-visible tools, JSON schemas, and mappings from tools to supported runtime capabilities.", "capability-catalogs": "Capability catalogs contain security probes for runtime actions implemented by the control plane. Unknown actions are rejected.", workflows: "Drag an agent onto a stage to reassign it. The backend revalidates the DAG, artifacts, handoffs, and stage ownership before saving.", policies: "Governance policies map supported runtime actions to allow, deny, or approval decisions. Unknown actions are rejected.", "evaluation-suites": "An evaluation suite is a reusable set of scenarios and pass thresholds. Datasets materialize a suite for one agent version; runs execute a frozen dataset." })[kind]; }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
