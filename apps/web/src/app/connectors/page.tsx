"use client";

import {
  ArrowRight, CheckCircle2, Cloud, Github, Gitlab, Loader2, Plus,
  RefreshCw, ServerCog, ShieldCheck, Trash2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { API_URL, api, describeApiError } from "@/lib/api";
import type { Connector } from "@/lib/types";

const statusStyle: Record<string, string> = {
  ACTIVE: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
  PENDING_INSTALLATION: "border-amber-400/20 bg-amber-400/10 text-amber-200",
  REGISTERING: "border-blue-400/20 bg-blue-400/10 text-blue-200",
  FAILED: "border-red-400/20 bg-red-400/10 text-red-300",
};

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("AutoDev");
  const [organization, setOrganization] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      setConnectors(await api.connectors());
      setError("");
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
      const params = new URLSearchParams(window.location.search);
      if (params.get("github") === "app-created") {
        setNotice("GitHub App created. Install it on an account to activate this connection.");
      } else if (params.get("github") === "installed") {
        setNotice("GitHub connection installed and ready for repository discovery.");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function createGitHubConnection(event: React.FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams({ name });
    if (organization.trim()) params.set("organization", organization.trim());
    window.open(`${API_URL}/api/connectors/github/manifest/start?${params.toString()}`, "_self");
  }

  async function verify(id: string) {
    setBusy(id);
    setError("");
    try {
      const result = await api.verifyConnector(id);
      setNotice(`${result.app || "GitHub App"} verified successfully.`);
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setBusy("");
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Remove this connection from AutoDev? The GitHub App itself remains owned in GitHub until you delete it there.")) return;
    setBusy(id);
    setError("");
    try {
      await api.deleteConnector(id);
      await load();
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setBusy("");
    }
  }

  return <Shell>
    <div className="mx-auto max-w-6xl p-5 lg:p-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-medium uppercase tracking-[.18em] text-teal-300">Integrations</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Connections</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Manage source-control identities once, then reuse them when adding repositories. Secrets are encrypted in the control-plane database and never enter task sandboxes.</p>
        </div>
        <button onClick={() => setShowCreate((value) => !value)} className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-teal-200"><Plus className="size-4" />Create connection</button>
      </div>

      {notice && <div className="mt-6 flex items-center gap-2 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4 text-sm text-emerald-200"><CheckCircle2 className="size-4" />{notice}</div>}
      {error && <div className="mt-6 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-300">{error}</div>}

      {showCreate && <section className="mt-6 rounded-2xl border border-teal-300/15 bg-teal-300/[.035] p-5">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-white/[.06] p-2.5"><Github className="size-5" /></span>
          <div><h2 className="font-semibold">Create a GitHub connection</h2><p className="mt-1 text-xs leading-5 text-slate-500">AutoDev sends a reviewed manifest to GitHub. GitHub asks you to sign in and confirm the permissions, then returns generated credentials directly to AutoDev. A random suffix is added to the GitHub App name because App names are globally unique.</p></div>
        </div>
        <form onSubmit={createGitHubConnection} className="mt-5 grid gap-4 md:grid-cols-2">
          <label className="text-xs text-slate-400">Connection name<input required minLength={2} maxLength={60} value={name} onChange={(event) => setName(event.target.value)} className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50" /><span className="mt-1.5 block text-[10px] text-slate-600">The GitHub App will use this prefix plus a unique suffix.</span></label>
          <label className="text-xs text-slate-400">Create under organization <span className="text-slate-600">(optional)</span><input pattern="[A-Za-z0-9_.-]+" value={organization} onChange={(event) => setOrganization(event.target.value)} placeholder="Leave empty for your personal account" className="mt-2 w-full rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 text-sm outline-none focus:border-teal-300/50" /></label>
          <div className="md:col-span-2 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[.06] bg-black/15 p-4">
            <p className="max-w-2xl text-xs leading-5 text-slate-500"><ShieldCheck className="mr-1.5 inline size-4 text-teal-300" />Requests repository contents/workflows write, pull requests write, and actions/checks read. GitHub shows the exact grant before creation.</p>
            <button className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-950">Continue to GitHub <ArrowRight className="size-4" /></button>
          </div>
        </form>
      </section>}

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Configured connections</h2><button onClick={() => void load()} className="p-2 text-slate-500 hover:text-white" aria-label="Refresh connections"><RefreshCw className="size-4" /></button></div>
        <div className="grid gap-4 md:grid-cols-2">
          {connectors.map((connector) => <article key={connector.id} className="rounded-xl border border-white/[.07] bg-[#0d121b]/90 p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex gap-3"><span className="rounded-xl border border-white/[.07] bg-black/20 p-2.5"><Github className="size-5" /></span><div><h3 className="font-medium">{connector.name}</h3><p className="mt-1 font-mono text-[11px] text-slate-600">{String(connector.metadata.app_slug || connector.id)}</p></div></div>
              <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold ${statusStyle[connector.status] || statusStyle.REGISTERING}`}>{connector.status.replaceAll("_", " ")}</span>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3 rounded-lg bg-black/15 p-3 text-xs"><div><p className="text-slate-600">Provider</p><p className="mt-1 text-slate-300">GitHub App</p></div><div><p className="text-slate-600">Installed account</p><p className="mt-1 text-slate-300">{connector.account_login || "Not installed"}</p></div></div>
            <div className="mt-4 flex flex-wrap gap-2">
              {connector.status === "PENDING_INSTALLATION" && <a href={`${API_URL}/api/connectors/${encodeURIComponent(connector.id)}/github/install`} className="rounded-lg bg-teal-300 px-3 py-2 text-xs font-semibold text-slate-950">Install on GitHub</a>}
              {connector.status === "ACTIVE" && <><Link href={`/repositories?connector=${encodeURIComponent(connector.id)}`} className="rounded-lg bg-teal-300 px-3 py-2 text-xs font-semibold text-slate-950">Add repository</Link><a href={`${API_URL}/api/connectors/${encodeURIComponent(connector.id)}/github/install`} className="rounded-lg border border-white/[.09] px-3 py-2 text-xs text-slate-300">Add account</a><button disabled={busy === connector.id} onClick={() => void verify(connector.id)} className="rounded-lg border border-white/[.09] px-3 py-2 text-xs text-slate-300 disabled:opacity-50">{busy === connector.id ? <Loader2 className="size-3 animate-spin" /> : "Verify"}</button></>}
              <button disabled={busy === connector.id} onClick={() => void remove(connector.id)} className="ml-auto rounded-lg p-2 text-slate-600 hover:bg-red-400/5 hover:text-red-300" aria-label={`Remove ${connector.name}`}><Trash2 className="size-4" /></button>
            </div>
          </article>)}
          {!connectors.length && <div className="rounded-xl border border-dashed border-white/[.09] p-8 text-center text-sm text-slate-600 md:col-span-2">No connections yet. Create the GitHub App without editing environment files.</div>}
        </div>
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-white/[.06] p-5 opacity-60"><div className="flex items-center gap-3"><Gitlab className="size-5 text-orange-300" /><div><h3 className="text-sm font-medium">GitLab</h3><p className="text-xs text-slate-600">Provider adapter coming later</p></div></div></div>
        <div className="rounded-xl border border-white/[.06] p-5 opacity-60"><div className="flex items-center gap-3"><Cloud className="size-5 text-blue-300" /><div><h3 className="text-sm font-medium">Azure DevOps</h3><p className="text-xs text-slate-600">Provider adapter coming later</p></div></div></div>
      </section>
      <div className="mt-6 flex items-center gap-2 text-xs text-slate-600"><ServerCog className="size-4" />Provider-neutral connection records are ready for additional adapters.</div>
    </div>
  </Shell>;
}
