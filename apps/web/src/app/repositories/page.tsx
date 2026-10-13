"use client";

import {
  Check, ChevronDown, ExternalLink, FolderGit2, Github, Globe2, KeyRound,
  Link2, Loader2, LockKeyhole, Plus, Search, Trash2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { Connector, ConnectorAccount, GitHubRepository, Project } from "@/lib/types";

export default function RepositoriesPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [accounts, setAccounts] = useState<ConnectorAccount[]>([]);
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]);
  const [connectorId, setConnectorId] = useState("");
  const [account, setAccount] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<GitHubRepository | null>(null);
  const [transport, setTransport] = useState<"ssh" | "https">("ssh");
  const [showAdd, setShowAdd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeConnectors = useMemo(
    () => connectors.filter((item) => item.provider === "github" && item.status === "ACTIVE"),
    [connectors],
  );

  const load = useCallback(async () => {
    try {
      const [projectList, connectorList] = await Promise.all([api.projects(), api.connectors()]);
      setProjects(projectList);
      setConnectors(connectorList);
      const requested = new URLSearchParams(window.location.search).get("connector") || "";
      const initial = connectorList.find((item) => item.id === requested && item.status === "ACTIVE") || connectorList.find((item) => item.provider === "github" && item.status === "ACTIVE");
      if (initial) {
        setConnectorId((current) => current || initial.id);
        if (requested) setShowAdd(true);
      }
      setError("");
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!connectorId) return;
    let cancelled = false;
    void api.connectorAccounts(connectorId).then((result) => {
      if (cancelled) return;
      setAccounts(result.accounts);
      setAccount((current) => result.accounts.some((item) => item.login === current) ? current : result.accounts[0]?.login || "");
    }).catch((cause) => { if (!cancelled) setError(describeApiError(cause)); });
    return () => { cancelled = true; };
  }, [connectorId]);

  useEffect(() => {
    if (!connectorId || !account || !showAdd) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setBusy(true);
      void api.connectorRepositories(connectorId, account, query.trim())
        .then((result) => { setRepositories(result.repositories); setError(""); })
        .catch((cause) => setError(describeApiError(cause)))
        .finally(() => setBusy(false));
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [account, connectorId, query, showAdd]);

  async function addRepository() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const project = await api.createProject({
        name: selected.full_name,
        repository_path: selected.full_name,
        source_type: "github",
        repository_url: selected.clone_url,
        default_branch: selected.default_branch,
        connector_id: connectorId,
        transport,
      });
      setProjects((current) => [...current, project].sort((a, b) => a.name.localeCompare(b.name)));
      setNotice(`${selected.full_name} added with ${transport.toUpperCase()} Git transport.`);
      setSelected(null);
      setQuery("");
      setShowAdd(false);
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  async function removeRepository(project: Project) {
    const confirmed = window.confirm(
      `Remove "${project.name}" from AutoDev?\n\n` +
      "All tasks attached to this repository, including their history, artifacts, " +
      "workspaces, and evidence, will be permanently deleted. The source repository " +
      "itself will not be deleted.",
    );
    if (!confirmed) return;
    setRemovingId(project.id);
    setError("");
    setNotice("");
    try {
      await api.deleteProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setNotice(`${project.name} and all attached tasks were removed from AutoDev.`);
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setRemovingId(null);
    }
  }

  return <Shell>
    <div className="mx-auto max-w-7xl p-5 lg:p-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div><p className="text-xs font-medium uppercase tracking-[.18em] text-teal-300">Workspace sources</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Repositories</h1><p className="mt-2 text-sm text-slate-500">Discover repositories through managed connections and choose Git transport per repository.</p></div>
        <button onClick={() => setShowAdd((value) => !value)} className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-teal-200"><Plus className="size-4" />Add GitHub repository</button>
      </div>

      {notice && <div className="mt-6 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4 text-sm text-emerald-200">{notice}</div>}
      {error && <div className="mt-6 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-300">{error}</div>}

      {showAdd && <section className="mt-6 rounded-2xl border border-white/[.08] bg-[#0d121b]/95 p-5">
        <div className="flex items-start justify-between gap-4"><div><h2 className="font-semibold">Add from GitHub</h2><p className="mt-1 text-xs text-slate-500">Connection → installed account → repository → transport</p></div><Github className="size-5 text-slate-500" /></div>
        {!activeConnectors.length ? <div className="mt-5 rounded-xl border border-amber-400/15 bg-amber-400/5 p-5"><p className="text-sm text-amber-100">A GitHub connection is required before private repository discovery.</p><Link href="/connectors" className="mt-3 inline-flex items-center gap-2 rounded-lg bg-teal-300 px-3 py-2 text-xs font-semibold text-slate-950">Create GitHub connection</Link></div> : <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div className="space-y-4">
            <label className="block text-xs text-slate-400">Connection<div className="relative mt-2"><select value={connectorId} onChange={(event) => { setConnectorId(event.target.value); setAccounts([]); setAccount(""); setRepositories([]); setSelected(null); }} className="w-full appearance-none rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50">{activeConnectors.map((connector) => <option key={connector.id} value={connector.id}>{connector.name} · {connector.account_login}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3 size-4 text-slate-600" /></div></label>
            <label className="block text-xs text-slate-400">Account or organization<div className="relative mt-2"><select value={account} onChange={(event) => { setAccount(event.target.value); setRepositories([]); setSelected(null); }} className="w-full appearance-none rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50">{accounts.map((item) => <option key={item.installation_id} value={item.login}>{item.login} · {item.type}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3 size-4 text-slate-600" /></div></label>
            <label className="block text-xs text-slate-400">Find repository<div className="relative mt-2"><Search className="absolute left-3 top-3 size-4 text-slate-600" /><input value={query} onChange={(event) => { setQuery(event.target.value); setSelected(null); }} placeholder="Type a repository name" className="w-full rounded-lg border border-white/[.09] bg-black/20 py-2.5 pl-10 pr-10 text-sm outline-none focus:border-teal-300/50" />{busy && <Loader2 className="absolute right-3 top-3 size-4 animate-spin text-teal-300" />}</div></label>
            <div className="max-h-64 space-y-1 overflow-y-auto rounded-xl border border-white/[.06] bg-black/15 p-2">
              {repositories.map((repository) => <button key={repository.full_name} onClick={() => { setSelected(repository); setQuery(repository.full_name); }} className={`flex w-full items-center justify-between rounded-lg p-3 text-left ${selected?.full_name === repository.full_name ? "bg-teal-300/10 text-teal-100" : "hover:bg-white/[.04]"}`}><span><span className="block text-sm">{repository.full_name}</span><span className="mt-1 block text-[10px] text-slate-600">{repository.default_branch || "Empty repository"} · updated {new Date(repository.updated_at).toLocaleDateString()}</span></span><span className="ml-3 flex items-center gap-1 text-[10px] text-slate-500">{repository.private ? <LockKeyhole className="size-3" /> : <Globe2 className="size-3" />}{selected?.full_name === repository.full_name && <Check className="ml-2 size-4 text-teal-300" />}</span></button>)}
              {!busy && !repositories.length && <p className="p-5 text-center text-xs text-slate-600">No accessible repositories match this account and query.</p>}
            </div>
          </div>
          <div className="rounded-xl border border-white/[.06] bg-black/10 p-4">
            <h3 className="text-sm font-medium">Git transport</h3><p className="mt-1 text-xs leading-5 text-slate-600">API operations such as pull requests still use the selected GitHub App connection.</p>
            <div className="mt-4 space-y-2">
              <button onClick={() => setTransport("ssh")} className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left ${transport === "ssh" ? "border-teal-300/30 bg-teal-300/[.06]" : "border-white/[.07]"}`}><KeyRound className="mt-0.5 size-4 text-teal-300" /><span><span className="block text-sm font-medium">SSH <span className="ml-1 text-[10px] text-teal-300">DEFAULT</span></span><span className="mt-1 block text-xs leading-5 text-slate-600">Uses the control-plane SSH agent or key for clone and push. Best when your deployment already manages host keys.</span></span></button>
              <button onClick={() => setTransport("https")} className={`flex w-full items-start gap-3 rounded-xl border p-4 text-left ${transport === "https" ? "border-teal-300/30 bg-teal-300/[.06]" : "border-white/[.07]"}`}><Link2 className="mt-0.5 size-4 text-blue-300" /><span><span className="block text-sm font-medium">HTTPS</span><span className="mt-1 block text-xs leading-5 text-slate-600">Uses just-in-time installation tokens. Choose this when no SSH key is mounted.</span></span></button>
            </div>
            {selected ? <div className="mt-5 rounded-lg border border-white/[.06] p-3"><p className="text-xs text-slate-500">Selected</p><p className="mt-1 text-sm text-slate-200">{selected.full_name}</p><p className="mt-1 truncate font-mono text-[10px] text-slate-600">{transport === "ssh" ? selected.ssh_url : selected.clone_url}</p></div> : <p className="mt-5 rounded-lg border border-dashed border-white/[.07] p-4 text-center text-xs text-slate-600">Select a repository to continue.</p>}
            <button disabled={!selected || busy} onClick={() => void addRepository()} className="mt-4 w-full rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40">Add repository</button>
          </div>
        </div>}
      </section>}

      <section className="mt-8 overflow-hidden rounded-xl border border-white/[.07] bg-[#0d121b]/90">
        <div className="flex items-center justify-between border-b border-white/[.07] px-5 py-4"><div><h2 className="text-sm font-semibold">Connected repositories</h2><p className="mt-1 text-xs text-slate-600">Removing a repository permanently removes all tasks attached to it.</p></div><span className="font-mono text-xs text-slate-600">{projects.length}</span></div>
        <div className="divide-y divide-white/[.05]">{projects.map((project) => <div key={project.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_140px_120px_72px] sm:items-center"><div className="flex items-center gap-3"><span className="rounded-lg bg-white/[.04] p-2"><FolderGit2 className="size-4 text-teal-300" /></span><div><p className="text-sm text-slate-200">{project.name}</p><p className="mt-1 truncate font-mono text-[10px] text-slate-600">{project.repository_url || project.repository_path || "Empty workspace"}</p></div></div><span className="text-xs text-slate-500">{project.default_branch || "No default branch"}</span><span className="w-fit rounded-full border border-white/[.07] px-2.5 py-1 text-[10px] uppercase text-slate-400">{project.source_type === "github" ? project.transport : project.source_type}</span><span className="flex items-center justify-end gap-2">{project.repository_url && <a href={project.repository_url.replace(/\.git$/, "")} target="_blank" rel="noreferrer" aria-label={`Open ${project.name}`} className="text-slate-600 hover:text-teal-300"><ExternalLink className="size-4" /></a>}<button disabled={removingId !== null} onClick={() => void removeRepository(project)} aria-label={`Remove ${project.name}`} className="rounded-lg p-2 text-slate-600 hover:bg-red-400/5 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40">{removingId === project.id ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}</button></span></div>)}{!projects.length && <p className="p-8 text-center text-sm text-slate-600">No repositories connected.</p>}</div>
      </section>
    </div>
  </Shell>;
}
