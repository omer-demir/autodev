"use client";

import { FilePlus2, FolderGit2, Github, Globe2, LockKeyhole, Search, X } from "lucide-react";
import { useState } from "react";
import { API_URL, api } from "@/lib/api";
import type { GitHubRepository, Project, RuntimeStatus } from "@/lib/types";

interface Props {
  runtime: RuntimeStatus | null;
  onClose: () => void;
  onConnected: (project: Project) => void;
}

export function RepositoryConnectorDialog({ runtime, onClose, onConnected }: Props) {
  const [source, setSource] = useState<"empty" | "local" | "github">("github");
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [url, setUrl] = useState("");
  const [owner, setOwner] = useState(runtime?.github_login || "");
  const [repos, setRepos] = useState<GitHubRepository[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function connect(repository: GitHubRepository) {
    setBusy(true);
    setError("");
    try {
      onConnected(await api.createProject({
        name: repository.full_name,
        repository_path: repository.full_name,
        source_type: "github",
        repository_url: repository.clone_url,
        default_branch: repository.default_branch,
      }));
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  }

  async function addLocal(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const name = path.replace(/\/$/, "").split("/").at(-1) || "Local repository";
      onConnected(await api.createProject({
        name, repository_path: path, source_type: "local",
        repository_url: null, default_branch: null,
      }));
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  }

  async function addEmpty(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onConnected(await api.createProject({
        name, repository_path: "", source_type: "empty",
        repository_url: null, default_branch: null,
      }));
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  }

  async function addGitHubUrl(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await connect(await api.githubRepository(url));
    } catch (reason) {
      setError(String(reason));
      setBusy(false);
    }
  }

  async function searchGitHub(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setRepos((await api.githubRepositories(owner)).repositories);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    await api.disconnectGitHub();
    window.location.reload();
  }

  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/[.09] bg-[#101620] p-6 shadow-2xl">
      <div className="flex justify-between">
        <div><p className="text-xs font-medium text-teal-300">WORKSPACE SOURCE</p><h2 className="mt-1 text-xl font-semibold">Choose where the task starts</h2></div>
        <button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/[.06] hover:text-white"><X className="size-4" /></button>
      </div>
      <div className="mt-5 flex rounded-lg bg-black/20 p-1">
        <button onClick={() => setSource("github")} className={`flex-1 rounded-md py-2 text-xs ${source === "github" ? "bg-white/[.08] text-white" : "text-slate-500"}`}><Github className="mr-2 inline size-3.5" />GitHub</button>
        <button onClick={() => setSource("local")} className={`flex-1 rounded-md py-2 text-xs ${source === "local" ? "bg-white/[.08] text-white" : "text-slate-500"}`}><FolderGit2 className="mr-2 inline size-3.5" />Local Git repository</button>
        <button onClick={() => setSource("empty")} className={`flex-1 rounded-md py-2 text-xs ${source === "empty" ? "bg-white/[.08] text-white" : "text-slate-500"}`}><FilePlus2 className="mr-2 inline size-3.5" />Empty workspace</button>
      </div>

      {source === "empty" ? <form onSubmit={addEmpty} className="mt-5">
        <label className="text-xs text-slate-400">Workspace name<input required minLength={2} value={name} onChange={(event) => setName(event.target.value)} placeholder="New product discovery" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50" /></label>
        <p className="mt-3 text-xs leading-5 text-slate-600">Starts an isolated Git workspace with no remote or default branch. Use an assessment task to capture research and context, then continue the durable session with another promoted agent.</p>
        <button disabled={busy} className="mt-5 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Create empty workspace</button>
      </form> : source === "local" ? <form onSubmit={addLocal} className="mt-5">
        <label className="text-xs text-slate-400">Absolute path visible to the control plane<input required value={path} onChange={(event) => setPath(event.target.value)} placeholder="/workspaces/my-repository" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 font-mono text-sm outline-none focus:border-teal-300/50" /></label>
        <p className="mt-3 text-xs leading-5 text-slate-600">The Workbench clones this repository into an isolated task worktree. Your original checkout is not modified.</p>
        <button disabled={busy} className="mt-5 rounded-lg bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Connect local repository</button>
      </form> : <div className="mt-5 space-y-5">
        <section className="rounded-xl border border-teal-300/15 bg-teal-300/[.035] p-4">
          <div className="flex items-center gap-2"><Globe2 className="size-4 text-teal-300" /><h3 className="text-sm font-medium">Start with a public URL</h3></div>
          <form onSubmit={addGitHubUrl} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input required type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/owner/repository" className="min-w-0 flex-1 rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 font-mono text-sm outline-none focus:border-teal-300/50" />
            <button disabled={busy} className="rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50">Connect URL</button>
          </form>
          <p className="mt-2 text-[11px] text-slate-600">No GitHub login is needed for a public repository.</p>
        </section>

        <section className="rounded-xl border border-white/[.07] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h3 className="text-sm font-medium">Private repositories and governed publication</h3><p className="mt-1 text-xs text-slate-600">GitHub App tokens are repository-scoped, expire after one hour, and are never mounted into sandboxes.</p></div>
            {runtime?.github_authenticated ? <div className="flex items-center gap-2"><span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs text-emerald-300">{runtime.github_auth_method === "github_app" ? `${runtime.github_app_slug || "AutoDev"} · ${runtime.github_login}` : runtime.github_login ? `@${runtime.github_login}` : "Token connected"}</span>{["github_app", "oauth"].includes(runtime.github_auth_method || "") && <button disabled={busy} onClick={disconnect} className="text-xs text-slate-500 hover:text-white">Disconnect</button>}</div> : runtime?.github_app_configured ? <a href={`${API_URL}/api/connectors/github/app/start`} className="inline-flex items-center gap-2 rounded-lg border border-teal-300/20 bg-teal-300/[.06] px-4 py-2 text-sm text-teal-100 hover:border-teal-300/40"><Github className="size-4" />Install AutoDev GitHub App</a> : runtime?.github_oauth_configured ? <a href={`${API_URL}/api/connectors/github/oauth/start`} className="inline-flex items-center gap-2 rounded-lg border border-white/[.09] bg-white/[.05] px-4 py-2 text-sm hover:border-teal-300/30"><Github className="size-4" />Connect GitHub</a> : <span className="rounded-lg border border-amber-400/15 bg-amber-400/5 px-3 py-2 text-xs text-amber-200">GitHub App setup required</span>}
          </div>
          {!runtime?.github_app_configured && !runtime?.github_authenticated && <p className="mt-3 text-xs leading-5 text-slate-600">Register the AutoDev GitHub App for bot-attributed commits and pull requests without sharing user SSH keys or personal tokens. OAuth and <span className="font-mono text-slate-400">WORKBENCH_GITHUB_TOKEN</span> remain compatibility fallbacks.</p>}
        </section>

        <form onSubmit={searchGitHub} className="flex gap-2">
          <input required value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="GitHub user or organization" className="min-w-0 flex-1 rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50" />
          <button disabled={busy} className="rounded-lg border border-white/[.09] px-4 py-2 text-sm disabled:opacity-50"><Search className="mr-2 inline size-4" />Browse</button>
        </form>
        <div className="space-y-2">{repos.map((repository) => <button key={repository.full_name} disabled={busy} onClick={() => connect(repository)} className="flex w-full items-center justify-between rounded-lg border border-white/[.06] bg-black/15 p-3 text-left hover:border-teal-300/20 disabled:opacity-50"><div><p className="text-sm text-slate-200">{repository.full_name}</p><p className="mt-1 text-[11px] text-slate-600">Default branch: {repository.default_branch}</p></div><span className="flex items-center gap-1 text-[10px] text-slate-500">{repository.private ? <LockKeyhole className="size-3" /> : <Globe2 className="size-3" />}{repository.private ? "Private" : "Public"}</span></button>)}</div>
      </div>}
      {error && <p className="mt-4 rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-300">{error}</p>}
    </div>
  </div>;
}