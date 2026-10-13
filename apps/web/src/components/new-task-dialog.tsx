"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { Project, RegistryDefinition, RuntimeStatus } from "@/lib/types";

interface WorkflowStage {
  id: string;
  agent: string;
  responsibility: string;
}

export function NewTaskDialog({ projects, runtime, agents, workflows, onClose }: { projects: Project[]; runtime: RuntimeStatus | null; agents: RegistryDefinition[]; workflows: RegistryDefinition[]; onClose: () => void }) {
  const router = useRouter();
  const runnable = agents.filter(agentCanExecute);
  const activeWorkflows = workflows.filter((workflow) => workflow.data.status === "active");
  const initialWorkflow = activeWorkflows.find((workflow) => workflow.id === "sdlc") || activeWorkflows[0];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    project_id: projects[0]?.id || 0,
    title: "",
    description: "",
    model_name: runtime?.configured_model || "",
    workflow_id: initialWorkflow?.id || "sdlc",
    agent_id: workflowOwnerAgent(initialWorkflow, agents, runnable[0]?.id),
    mode: (projects[0]?.source_type === "empty" ? "assessment" : workflowDefaultMode(initialWorkflow)) as "change" | "assessment",
    verbose_logging: false,
  });
  const selectedWorkflow = activeWorkflows.find((workflow) => workflow.id === form.workflow_id);
  const stages = Array.isArray(selectedWorkflow?.data.stages) ? selectedWorkflow.data.stages as unknown as WorkflowStage[] : [];
  const requiredAgentIds = [...new Set(stages.map((stage) => stage.agent.replace(/^did:local:/, "")))];
  const unavailableAgents = requiredAgentIds.filter((agentId) => !agentCanExecute(agents.find((agent) => agent.id === agentId)));
  const workflowReady = stages.length ? unavailableAgents.length === 0 : runnable.length > 0;
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const task = await api.createTask(form); await api.runTask(task.id); router.push(`/tasks/${task.id}`); }
    catch (reason) { setError(String(reason)); setBusy(false); }
  }
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><form onSubmit={submit} className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-white/[.09] bg-[#101620] p-6 shadow-2xl"><div className="flex items-start justify-between"><div><p className="text-xs font-medium text-teal-300">NEW TASK</p><h2 className="mt-1 text-xl font-semibold">What should the workflow accomplish?</h2></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.06] hover:text-white"><X className="size-4" /></button></div><div className="mt-6 space-y-4">
    <label className="block text-xs text-slate-400">Workspace<select required value={form.project_id} onChange={(event) => { const project = projects.find((item) => item.id === Number(event.target.value)); const mode = project?.source_type === "empty" ? "assessment" : workflowDefaultMode(selectedWorkflow); setForm({ ...form, project_id: Number(event.target.value), mode }); }} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value={0} disabled>Choose a workspace source</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.source_type}</option>)}</select></label>
    <label className="block text-xs text-slate-400">Workflow<select required value={form.workflow_id} onChange={(event) => { const workflowId = event.target.value; const workflow = activeWorkflows.find((item) => item.id === workflowId); const project = projects.find((item) => item.id === form.project_id); const mode = project?.source_type === "empty" ? "assessment" : workflowDefaultMode(workflow); setForm({ ...form, workflow_id: workflowId, agent_id: workflowOwnerAgent(workflow, agents, runnable[0]?.id), mode }); }} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm">{activeWorkflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{String(workflow.data.name)} · v{String(workflow.data.version)}</option>)}</select></label>
    {stages.length ? <div className="border-y border-white/[.07] py-3"><div className="flex items-center justify-between text-xs"><span className="text-slate-400">Assigned stages</span><span className={workflowReady ? "text-emerald-300" : "text-amber-300"}>{workflowReady ? "Ready" : `${unavailableAgents.length} role${unavailableAgents.length === 1 ? "" : "s"} unavailable`}</span></div><div className="mt-3 space-y-2">{stages.map((stage, index) => { const agentId = stage.agent.replace(/^did:local:/, ""); const agent = agents.find((item) => item.id === agentId); const ready = agentCanExecute(agent); const readiness = agent?.data.status === "promoted" ? "promoted" : agent?.data.evaluation_required === false ? "evaluation bypass" : "draft"; return <div key={stage.id} className="grid grid-cols-[24px_1fr_auto] items-start gap-2 text-xs"><span className="font-mono text-slate-600">{index + 1}</span><div><p className="text-slate-300">{stage.id.replaceAll("-", " ")}</p><p className="mt-0.5 line-clamp-2 text-slate-600">{stage.responsibility}</p></div><span className={ready ? "text-emerald-300" : "text-amber-300"}>{String(agent?.data.name || agentId)} · {readiness}</span></div>; })}</div></div> : <label className="block text-xs text-slate-400">Runnable agent<select value={form.agent_id} onChange={(event) => setForm({ ...form, agent_id: event.target.value })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm">{runnable.map((agent) => <option key={agent.id} value={`did:local:${agent.id}`}>{String(agent.data.name)} · v{String(agent.data.version)}{agent.data.evaluation_required === false ? " · evaluation bypass" : ""}</option>)}</select></label>}
    <label className="block text-xs text-slate-400">Task mode<select value={form.mode} onChange={(event) => setForm({ ...form, mode: event.target.value as "change" | "assessment" })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value="change">Change repository</option><option value="assessment">Read-only assessment</option></select></label>
    <label className="block text-xs text-slate-400">Model<select value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value={runtime?.configured_model || ""}>{runtime?.configured_model || "Configured default"}</option>{runtime?.models.filter((model) => model.name !== runtime.configured_model).map((model) => <option key={model.name}>{model.name}</option>)}</select></label>
    <label className="flex items-start gap-3 rounded-lg border border-amber-300/15 bg-amber-300/[.03] p-3 text-xs text-slate-400"><input type="checkbox" checked={form.verbose_logging} onChange={(event) => setForm({ ...form, verbose_logging: event.target.checked })} className="mt-0.5" /><span><strong className="block text-amber-200">Verbose LLM trace</strong><span className="mt-1 block leading-5">Stream complete prompts and raw responses to the task Model log. This can expose repository content and instructions.</span></span></label>
    <label className="block text-xs text-slate-400">Task title<input required minLength={3} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Migrate this repository to Vue" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm" /></label>
    <label className="block text-xs text-slate-400">Description<textarea required minLength={3} rows={5} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Describe constraints and acceptance criteria." className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm" /></label>
  </div>{!workflowReady && <p className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-amber-200">Promote the assigned {unavailableAgents.join(", ")} role{unavailableAgents.length === 1 ? "" : "s"} after behavioral evaluation, or have an administrator approve an evaluation bypass.</p>}{error && <p className="mt-4 rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-300">{error}</p>}<div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded-lg border border-white/[.08] px-4 py-2 text-sm">Cancel</button><button disabled={busy || !projects.length || !workflowReady} className="rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Create and run</button></div></form></div>;
}

function agentCanExecute(agent: RegistryDefinition | undefined): boolean {
  return agent?.data.status === "promoted" || agent?.data.evaluation_required === false;
}

function workflowDefaultMode(workflow: RegistryDefinition | undefined): "change" | "assessment" {
  return workflow?.data.default_mode === "assessment" ? "assessment" : "change";
}

function workflowOwnerAgent(workflow: RegistryDefinition | undefined, agents: RegistryDefinition[], fallbackAgentId = "developer"): string {
  const stages = Array.isArray(workflow?.data.stages) ? workflow.data.stages as unknown as WorkflowStage[] : [];
  const owner = stages.find((stage) => {
    const agentId = stage.agent.replace(/^did:local:/, "");
    const capabilities = agents.find((agent) => agent.id === agentId)?.data.capabilities;
    return Array.isArray(capabilities) && capabilities.includes("repository.write");
  });
  return String(owner?.agent || workflow?.data.default_agent || stages[0]?.agent || `did:local:${fallbackAgentId}`);
}
