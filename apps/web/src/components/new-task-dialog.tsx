"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { Project, RegistryDefinition, RuntimeStatus } from "@/lib/types";

export function NewTaskDialog({ projects, runtime, agents, onClose }: { projects: Project[]; runtime: RuntimeStatus | null; agents: RegistryDefinition[]; onClose: () => void }) {
  const router = useRouter();
  const promoted = agents.filter((agent) => agent.data.status === "promoted");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    project_id: projects[0]?.id || 0,
    title: "",
    description: "",
    model_name: runtime?.configured_model || "",
    agent_id: `did:local:${promoted[0]?.id || "developer"}`,
    mode: "change" as "change" | "assessment",
    verbose_logging: false,
  });
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const task = await api.createTask(form); await api.runTask(task.id); router.push(`/tasks/${task.id}`); }
    catch (reason) { setError(String(reason)); setBusy(false); }
  }
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}><form onSubmit={submit} className="w-full max-w-lg rounded-2xl border border-white/[.09] bg-[#101620] p-6 shadow-2xl"><div className="flex items-start justify-between"><div><p className="text-xs font-medium text-teal-300">NEW SDLC TASK</p><h2 className="mt-1 text-xl font-semibold">What should the agent build?</h2></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.06] hover:text-white"><X className="size-4" /></button></div><div className="mt-6 space-y-4">
    <label className="block text-xs text-slate-400">Repository<select required value={form.project_id} onChange={(event) => setForm({ ...form, project_id: Number(event.target.value) })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value={0} disabled>Choose a connected repository</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.source_type}</option>)}</select></label>
    <label className="block text-xs text-slate-400">Promoted agent<select value={form.agent_id} onChange={(event) => setForm({ ...form, agent_id: event.target.value })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm">{promoted.map((agent) => <option key={agent.id} value={`did:local:${agent.id}`}>{String(agent.data.name)} · v{String(agent.data.version)}</option>)}</select></label>
    <label className="block text-xs text-slate-400">Task mode<select value={form.mode} onChange={(event) => setForm({ ...form, mode: event.target.value as "change" | "assessment" })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value="change">Change repository</option><option value="assessment">Read-only assessment</option></select></label>
    <label className="block text-xs text-slate-400">Model<select value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm"><option value={runtime?.configured_model || ""}>{runtime?.configured_model || "Configured default"}</option>{runtime?.models.filter((model) => model.name !== runtime.configured_model).map((model) => <option key={model.name}>{model.name}</option>)}</select></label>
    <label className="flex items-start gap-3 rounded-lg border border-amber-300/15 bg-amber-300/[.03] p-3 text-xs text-slate-400"><input type="checkbox" checked={form.verbose_logging} onChange={(event) => setForm({ ...form, verbose_logging: event.target.checked })} className="mt-0.5" /><span><strong className="block text-amber-200">Verbose LLM trace</strong><span className="mt-1 block leading-5">Stream complete prompts and raw responses to the task Model log. This can expose repository content and instructions.</span></span></label>
    <label className="block text-xs text-slate-400">Task title<input required minLength={3} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="Migrate this repository to Vue" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm" /></label>
    <label className="block text-xs text-slate-400">Description<textarea required minLength={3} rows={5} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Describe constraints and acceptance criteria." className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm" /></label>
  </div>{error && <p className="mt-4 rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-300">{error}</p>}<div className="mt-6 flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded-lg border border-white/[.08] px-4 py-2 text-sm">Cancel</button><button disabled={busy || !projects.length || !promoted.length} className="rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Create and run</button></div></form></div>;
}
