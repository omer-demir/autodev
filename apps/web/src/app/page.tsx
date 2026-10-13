"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity, ArrowUpRight, Bot, CheckCircle2, CircleDot, Clock3, GitBranch,
  FolderGit2, Github, Globe2, LockKeyhole, Plus, Search, ShieldAlert, Sparkles, X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { NewTaskDialog } from "@/components/new-task-dialog";
import { useLiveEvents } from "@/hooks/use-live-events";
import { api, describeApiError } from "@/lib/api";
import type { DashboardData, GitHubRepository, Project, RegistryDefinition, RuntimeStatus, Task } from "@/lib/types";

const statusStyle: Record<string, string> = {
  DRAFT: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  DONE: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
  AWAITING_APPROVAL: "bg-amber-400/10 text-amber-300 border-amber-400/20",
  FAILED: "bg-red-400/10 text-red-300 border-red-400/20",
  CANCELLED: "bg-red-400/10 text-red-300 border-red-400/20",
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [runtimeChecked, setRuntimeChecked] = useState(false);
  const [runtimeError, setRuntimeError] = useState("");
  const [agents, setAgents] = useState<RegistryDefinition[]>([]);
  const [workflows, setWorkflows] = useState<RegistryDefinition[]>([]);
  const [error, setError] = useState("");
  const loadPending = useRef<Promise<void> | null>(null);
  const runtimePending = useRef<Promise<void> | null>(null);
  const load = useCallback(() => {
    if (loadPending.current) return loadPending.current;
    loadPending.current = Promise.all([api.dashboard(), api.projects(), api.registry("agents"), api.registry("workflows")])
      .then(([dashboard, projectList, agentList, workflowList]) => { setData(dashboard); setProjects(projectList); setAgents(agentList); setWorkflows(workflowList); setError(""); })
      .catch((cause) => setError(`Dashboard data refresh failed: ${describeApiError(cause)}`))
      .finally(() => { loadPending.current = null; });
    return loadPending.current;
  }, []);
  const loadRuntime = useCallback(() => {
    if (runtimePending.current) return runtimePending.current;
    runtimePending.current = api.runtime()
      .then((status) => { setRuntime(status); setRuntimeError(""); })
      .catch((cause) => { setRuntime(null); setRuntimeError(describeApiError(cause)); })
      .finally(() => { setRuntimeChecked(true); runtimePending.current = null; });
    return runtimePending.current;
  }, []);
  useLiveEvents(load);
  useEffect(() => {
    void load();
    void loadRuntime();
    const runtimeTimer = window.setInterval(() => { if (document.visibilityState === "visible") void loadRuntime(); }, 300_000);
    return () => { window.clearInterval(runtimeTimer); };
  }, [load, loadRuntime]);

  const metrics = [
    { label: "Active tasks", value: data?.metrics.active_tasks ?? 0, icon: Activity, color: "text-blue-300", glow: "from-blue-400/12" },
    { label: "Awaiting approval", value: data?.metrics.awaiting_approval ?? 0, icon: Clock3, color: "text-amber-300", glow: "from-amber-400/12" },
    { label: "Running agents", value: data?.metrics.running_agents ?? 0, icon: Bot, color: "text-teal-300", glow: "from-teal-400/12" },
    { label: "Security findings", value: data?.metrics.security_findings ?? 0, icon: ShieldAlert, color: "text-violet-300", glow: "from-violet-400/12" },
  ];

  return <Shell>
    <div className="mx-auto max-w-7xl p-5 lg:p-8">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div><div className="mb-2 flex items-center gap-2 text-xs font-medium text-teal-300"><Sparkles className="size-3.5" /> Local development environment</div><h1 className="text-3xl font-semibold tracking-tight">Good morning, developer.</h1><p className="mt-2 text-sm text-slate-500">Build, govern, and inspect agentic software changes.</p></div>
        <div className="flex gap-2"><Link href="/repositories" className="flex items-center justify-center gap-2 rounded-lg border border-white/[.09] bg-white/[.03] px-4 py-2.5 text-sm text-slate-300 hover:border-teal-300/30 hover:text-white"><FolderGit2 className="size-4" /> Manage repositories</Link><button onClick={() => setShowNew(true)} className="flex items-center justify-center gap-2 rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow-[0_10px_35px_rgba(94,234,212,.12)] hover:bg-teal-200"><Plus className="size-4" /> New task</button></div>
      </div>
      {error && <div className="mb-6 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-300">{error}</div>}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(({ label, value, icon: Icon, color, glow }) => <div key={label} className={`relative overflow-hidden rounded-xl border border-white/[.07] bg-gradient-to-br ${glow} to-[#0d121b] p-5`}><div className="flex items-start justify-between"><div><p className="text-xs text-slate-500">{label}</p><p className="mt-2 font-mono text-3xl font-medium">{value}</p></div><div className="rounded-lg border border-white/[.06] bg-black/20 p-2"><Icon className={`size-4 ${color}`} /></div></div><div className="mt-5 h-px bg-gradient-to-r from-white/10 to-transparent" /><p className="mt-3 text-[11px] text-slate-600">Live from control plane</p></div>)}
      </section>
      <div className="mt-8 grid gap-6 xl:grid-cols-[1fr_320px]">
        <section id="tasks" className="overflow-hidden rounded-xl border border-white/[.07] bg-[#0d121b]/90">
          <div className="flex items-center justify-between border-b border-white/[.07] px-5 py-4"><div><h2 className="text-sm font-semibold">Recent tasks</h2><p className="mt-1 text-xs text-slate-600">SDLC work tracked as durable tasks</p></div><span className="font-mono text-xs text-slate-600">{data?.tasks.length ?? 0} shown</span></div>
          <div className="divide-y divide-white/[.05]">{data?.tasks.map((task) => <TaskRow key={task.id} task={task} />)}{!data?.tasks.length && <p className="p-8 text-center text-sm text-slate-600">No tasks yet.</p>}</div>
        </section>
        <aside className="space-y-5">
          <div className="rounded-xl border border-white/[.07] bg-[#0d121b]/90 p-5"><div className="flex items-center gap-2"><span className={`size-2 rounded-full ${!runtimeChecked ? "animate-pulse bg-amber-300" : runtime?.docker_available ? "bg-emerald-400 shadow-[0_0_12px_#34d399]" : "bg-red-400"}`} /><h2 className="text-sm font-semibold">Runtime</h2></div><div className="mt-5 space-y-3 text-xs"><InfoRow label="Sandbox" value={!runtimeChecked ? "Checking…" : runtime?.docker_available ? "Docker ready" : runtime?.docker?.error || runtimeError || "Docker offline"} /><InfoRow label="Provider" value={!runtimeChecked ? "Checking…" : runtime?.model_available ? `${runtime.active_model_provider}${runtime.model_fallback_active ? " fallback" : " ready"}` : runtime?.model_error || runtimeError || "Not reachable"} /><InfoRow label="Model" value={!runtimeChecked ? "Checking…" : runtime?.model_fallback_active ? runtime.models[0]?.name || "—" : runtime?.configured_model || "—"} /><InfoRow label="Host credentials" value="Not mounted" good /></div></div>
          <div className="rounded-xl border border-teal-300/10 bg-teal-300/[.035] p-5"><CircleDot className="size-4 text-teal-300" /><h3 className="mt-3 text-sm font-semibold">Default-deny governance</h3><p className="mt-2 text-xs leading-5 text-slate-500">The agent can request capabilities. It cannot authorize itself. Sensitive Git actions pause for scoped approval.</p></div>
        </aside>
      </div>
    </div>
    {showNew && <NewTaskDialog projects={projects} runtime={runtime} agents={agents} workflows={workflows} onClose={() => setShowNew(false)} />}
  </Shell>;
}

function TaskRow({ task }: { task: Task }) {
  return <Link href={`/tasks/${task.id}`} className="group grid gap-3 px-5 py-4 hover:bg-white/[.025] sm:grid-cols-[64px_1fr_150px_36px] sm:items-center">
    <div title={task.id} className="font-mono text-xs text-slate-500">{task.id.slice(-5)}</div><div><h3 className="text-sm font-medium group-hover:text-teal-200">{task.title}</h3><p className="mt-1 flex items-center gap-1.5 text-xs text-slate-600"><GitBranch className="size-3" /> {task.branch}</p></div><div><span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold tracking-wide ${statusStyle[task.status] || "border-blue-400/20 bg-blue-400/10 text-blue-300"}`}>{task.status.replaceAll("_", " ")}</span><div className="mt-2 h-1 w-full rounded-full bg-white/[.05]"><div className="h-full rounded-full bg-teal-300" style={{ width: `${task.progress}%` }} /></div></div><ArrowUpRight className="size-4 text-slate-700 group-hover:text-teal-300" /></Link>;
}

function InfoRow({ label, value, good }: { label: string; value: string; good?: boolean }) { return <div className="flex justify-between"><span className="text-slate-600">{label}</span><span className={good ? "text-emerald-300" : "text-slate-300"}>{good && <CheckCircle2 className="mr-1 inline size-3" />}{value}</span></div>; }

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LegacyNewTask({ projects, runtime, onClose }: { projects: Project[]; runtime: RuntimeStatus | null; onClose: () => void }) {
  const router = useRouter(); const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ project_id: projects[0]?.id || 1, title: "", description: "", model_name: runtime?.configured_model || "" });
  async function submit(e: React.FormEvent) { e.preventDefault(); setBusy(true); try { const task = await api.createTask(form); await api.runTask(task.id); router.push(`/tasks/${task.id}`); } finally { setBusy(false); } }
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(e) => { if (e.currentTarget === e.target) onClose(); }}><form onSubmit={submit} className="w-full max-w-lg rounded-2xl border border-white/[.09] bg-[#101620] p-6 shadow-2xl"><div className="flex items-start justify-between"><div><p className="text-xs font-medium text-teal-300">NEW SDLC TASK</p><h2 className="mt-1 text-xl font-semibold">What should the agent build?</h2></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.06] hover:text-white"><X className="size-4" /></button></div><div className="mt-6 space-y-4"><label className="block text-xs text-slate-400">Repository<select required value={form.project_id} onChange={(e) => setForm({ ...form, project_id: Number(e.target.value) })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50"><option value="" disabled>Choose a connected repository</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.source_type}</option>)}</select></label><label className="block text-xs text-slate-400">Ollama model<select value={form.model_name} onChange={(e) => setForm({ ...form, model_name: e.target.value })} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50"><option value={runtime?.configured_model || ""}>{runtime?.configured_model || "Configured default"}{runtime?.models.some((m) => m.name === runtime.configured_model) ? " · installed" : " · not detected"}</option>{runtime?.models.filter((m) => m.name !== runtime.configured_model).map((model) => <option key={model.name} value={model.name}>{model.name}</option>)}</select></label><label className="block text-xs text-slate-400">Task title<input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Migrate this repository to Vue" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none placeholder:text-slate-700 focus:border-teal-300/50" /></label><label className="block text-xs text-slate-400">Requirements<textarea required minLength={3} rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Describe the exact migration, constraints, and acceptance criteria..." className="mt-2 w-full resize-none rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none placeholder:text-slate-700 focus:border-teal-300/50" /></label></div>{!runtime?.ollama_reachable && <p className="mt-4 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3 text-xs text-amber-300">Ollama is not reachable. The task will fail clearly until Ollama is started and the selected model is installed.</p>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-white/[.05]">Cancel</button><button disabled={busy || !projects.length} className="flex items-center gap-2 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-teal-200"><Sparkles className="size-4" />{busy ? "Starting…" : "Create & run"}</button></div></form></div>;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function LegacyRepositoryDialog({ runtime, onClose, onConnected }: { runtime: RuntimeStatus | null; onClose: () => void; onConnected: (project: Project) => void }) {
  const [source, setSource] = useState<"local" | "github">("local"); const [path, setPath] = useState(""); const [owner, setOwner] = useState(""); const [repos, setRepos] = useState<GitHubRepository[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function addLocal(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(""); try { const name = path.replace(/\/$/, "").split("/").at(-1) || "Local repository"; onConnected(await api.createProject({ name, repository_path: path, source_type: "local", repository_url: null, default_branch: null })); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } }
  async function searchGitHub(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(""); try { setRepos((await api.githubRepositories(owner)).repositories); } catch (reason) { setError(String(reason)); } finally { setBusy(false); } }
  async function connect(repository: GitHubRepository) { setBusy(true); try { onConnected(await api.createProject({ name: repository.full_name, repository_path: repository.full_name, source_type: "github", repository_url: repository.clone_url, default_branch: repository.default_branch })); } catch (reason) { setError(String(reason)); setBusy(false); } }
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"><div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/[.09] bg-[#101620] p-6"><div className="flex justify-between"><div><p className="text-xs font-medium text-teal-300">REPOSITORY CONNECTOR</p><h2 className="mt-1 text-xl font-semibold">Choose real source code</h2></div><button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.06]"><X className="size-4" /></button></div><div className="mt-5 flex rounded-lg bg-black/20 p-1"><button onClick={() => setSource("local")} className={`flex-1 rounded-md py-2 text-xs ${source === "local" ? "bg-white/[.08] text-white" : "text-slate-500"}`}><FolderGit2 className="mr-2 inline size-3.5" />Local Git repository</button><button onClick={() => setSource("github")} className={`flex-1 rounded-md py-2 text-xs ${source === "github" ? "bg-white/[.08] text-white" : "text-slate-500"}`}><Github className="mr-2 inline size-3.5" />GitHub</button></div>{source === "local" ? <form onSubmit={addLocal} className="mt-5"><label className="text-xs text-slate-400">Absolute path visible to the control plane<input required value={path} onChange={(e) => setPath(e.target.value)} placeholder="/workspaces/my-repository" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 font-mono text-sm outline-none focus:border-teal-300/50" /></label><p className="mt-3 text-xs leading-5 text-slate-600">The Workbench clones this repository into an isolated task worktree. Your original checkout is not modified.</p><button disabled={busy} className="mt-5 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950">Connect local repository</button></form> : <div className="mt-5"><form onSubmit={searchGitHub} className="flex gap-2"><input required value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="GitHub user or organization" className="flex-1 rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50" /><button disabled={busy} className="flex items-center gap-2 rounded-lg bg-teal-300 px-4 text-sm font-semibold text-slate-950"><Search className="size-4" />Find repos</button></form><p className="mt-3 flex items-center gap-2 text-xs text-slate-600">{runtime?.github_authenticated ? <><LockKeyhole className="size-3 text-emerald-400" />GitHub token configured; accessible private repositories are included.</> : <><Globe2 className="size-3" />Public repositories only. Set WORKBENCH_GITHUB_TOKEN for private repositories.</>}</p><div className="mt-4 divide-y divide-white/[.05] rounded-lg border border-white/[.07]">{repos.map((repo) => <button key={repo.full_name} disabled={busy} onClick={() => connect(repo)} className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-white/[.03]"><div><p className="text-sm">{repo.full_name}</p><p className="mt-1 text-[10px] text-slate-600">Default branch: {repo.default_branch}</p></div><span className="text-xs text-slate-500">{repo.private ? <LockKeyhole className="size-3.5" /> : <Globe2 className="size-3.5" />}</span></button>)}</div></div>}{error && <p className="mt-4 rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-300">{error}</p>}</div></div>;
}
