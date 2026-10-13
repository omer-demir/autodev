"use client";

import { useCallback, useEffect, useState } from "react";
import { Shield, Trash2, UserPlus, Users } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { OrganizationMember } from "@/lib/types";

const roles = ["viewer", "developer", "reviewer", "admin"] as const;

export default function AdminPage() {
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [form, setForm] = useState({ user_id: "", email: "", display_name: "", role: "viewer" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setMembers(await api.members()); setError(""); }
    catch (cause) { setError(describeApiError(cause)); }
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  async function addMember(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.createMember({ ...form, email: form.email || undefined, display_name: form.display_name || undefined });
      setForm({ user_id: "", email: "", display_name: "", role: "viewer" });
      await load();
    } catch (cause) { setError(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function updateRole(userId: string, role: string) {
    setBusy(true);
    try { await api.updateMember(userId, role); await load(); }
    catch (cause) { setError(describeApiError(cause)); } finally { setBusy(false); }
  }
  async function removeMember(userId: string) {
    setBusy(true);
    try { await api.deleteMember(userId); await load(); }
    catch (cause) { setError(describeApiError(cause)); } finally { setBusy(false); }
  }

  return <Shell><div className="mx-auto max-w-6xl p-5 lg:p-8">
    <div><p className="text-xs font-medium text-teal-300">ORGANIZATION</p><h1 className="mt-1 text-3xl font-semibold">Members</h1><p className="mt-2 text-sm text-slate-500">Control organization access and role-based permissions.</p></div>
    {error && <div className="mt-5 border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{error}</div>}
    <div className="mt-7 grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="overflow-hidden border border-white/[.07] bg-[#0d121b]">
        <div className="flex items-center gap-2 border-b border-white/[.07] px-5 py-4"><Users className="size-4 text-teal-300" /><h2 className="text-sm font-medium">Active memberships</h2><span className="ml-auto font-mono text-xs text-slate-600">{members.length}</span></div>
        {members.map((member) => <div key={member.user_id} className="grid gap-3 border-b border-white/[.05] px-5 py-4 last:border-0 sm:grid-cols-[1fr_150px_36px] sm:items-center"><div><p className="text-sm text-slate-200">{member.display_name || member.email || member.user_id}</p><p className="mt-1 font-mono text-[11px] text-slate-600">{member.user_id}{member.email ? ` · ${member.email}` : ""}</p></div><select aria-label={`Role for ${member.user_id}`} value={member.role} disabled={busy} onChange={(event) => void updateRole(member.user_id, event.target.value)} className="border border-white/[.08] bg-black/20 px-3 py-2 text-xs">{roles.map((role) => <option key={role}>{role}</option>)}</select><button title="Remove member" aria-label={`Remove ${member.user_id}`} disabled={busy} onClick={() => void removeMember(member.user_id)} className="p-2 text-slate-600 hover:text-red-300 disabled:opacity-40"><Trash2 className="size-4" /></button></div>)}
        {!members.length && <p className="p-10 text-center text-sm text-slate-600">No memberships found.</p>}
      </section>
      <form onSubmit={addMember} className="h-fit border border-white/[.07] bg-[#0d121b] p-5"><div className="flex items-center gap-2"><UserPlus className="size-4 text-blue-300" /><h2 className="text-sm font-medium">Add member</h2></div><div className="mt-5 space-y-4"><label className="block text-xs text-slate-500">OIDC subject or user ID<input required value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} className="mt-2 w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm" /></label><label className="block text-xs text-slate-500">Display name<input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} className="mt-2 w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm" /></label><label className="block text-xs text-slate-500">Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} className="mt-2 w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm" /></label><label className="block text-xs text-slate-500">Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} className="mt-2 w-full border border-white/[.08] bg-black/20 px-3 py-2 text-sm">{roles.map((role) => <option key={role}>{role}</option>)}</select></label></div><button disabled={busy} className="mt-5 inline-flex items-center gap-2 bg-teal-300 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"><Shield className="size-4" />Add membership</button></form>
    </div>
  </div></Shell>;
}
