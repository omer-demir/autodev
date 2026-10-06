"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, Blocks, Bot, Box, ChevronRight, CircleGauge, FileCheck2,
  Fingerprint, GitPullRequest, Hexagon, LockKeyhole, Scale, Settings, ShieldCheck,
  MessagesSquare,
} from "lucide-react";

const nav = [
  { label: "Workspace", items: [{ href: "/", label: "Dashboard", icon: CircleGauge }, { href: "/tasks", label: "Tasks", icon: FileCheck2 }, { href: "/sessions", label: "Sessions", icon: MessagesSquare }] },
  { label: "Runtime", items: [{ href: "/management", label: "Agents & tools", icon: Bot }, { href: "/sandboxes", label: "Sandboxes", icon: Box }] },
  { label: "Control", items: [{ href: "/evaluations", label: "Evaluations", icon: Fingerprint }, { href: "/security", label: "Security", icon: ShieldCheck }, { href: "/governance", label: "Governance", icon: Scale }, { href: "/evidence", label: "Evidence", icon: Blocks }] },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      <aside className="glass fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-white/[.07] lg:flex lg:flex-col">
        <Link href="/" className="flex h-17 items-center gap-3 border-b border-white/[.07] px-5">
          <span className="grid size-9 place-items-center rounded-xl bg-teal-300 text-slate-950 shadow-[0_0_30px_rgba(94,234,212,.18)]"><Hexagon className="size-5" strokeWidth={2.4} /></span>
          <span><b className="block text-sm tracking-tight">SDLC Workbench</b><small className="text-[10px] uppercase tracking-[.2em] text-slate-500">Local control plane</small></span>
        </Link>
        <nav className="flex-1 space-y-7 overflow-y-auto px-3 py-6">
          {nav.map((group) => <section key={group.label}>
            <h2 className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.18em] text-slate-600">{group.label}</h2>
            <div className="space-y-1">{group.items.map((item) => {
              const Icon = item.icon; const active = item.href === pathname || (item.href === "/" && pathname === "/");
              return <Link key={item.label} href={item.href} className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${active ? "bg-white/[.07] text-white" : "text-slate-400 hover:bg-white/[.04] hover:text-slate-200"}`}><Icon className={`size-4 ${active ? "text-teal-300" : "text-slate-500 group-hover:text-slate-300"}`} />{item.label}{active && <ChevronRight className="ml-auto size-3 text-slate-600" />}</Link>;
            })}</div>
          </section>)}
        </nav>
        <div className="m-3 rounded-xl border border-white/[.07] bg-black/20 p-3"><div className="flex items-center gap-2 text-xs font-medium"><span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_10px_#34d399]" />Local backend</div><p className="mt-2 text-[11px] leading-4 text-slate-500">Real execution · Default deny</p></div>
        <Link href="/management" className="flex items-center gap-3 border-t border-white/[.07] px-6 py-4 text-xs text-slate-500 hover:text-slate-200"><Settings className="size-4" />Management</Link>
      </aside>
      <div className="lg:pl-60">
        <header className="glass sticky top-0 z-20 flex h-17 items-center justify-between border-b border-white/[.07] px-5 lg:px-8">
          <div className="flex items-center gap-2 text-xs text-slate-500"><LockKeyhole className="size-3.5 text-teal-300" /> Governed execution <span className="text-slate-700">/</span> <span className="text-slate-300">development-v1</span></div>
          <div className="flex items-center gap-4"><div className="hidden items-center gap-2 rounded-full border border-white/[.08] bg-black/20 px-3 py-1.5 text-xs text-slate-400 sm:flex"><Activity className="size-3.5 text-emerald-400" /> All systems nominal</div><button aria-label="Pull requests" className="rounded-lg p-2 text-slate-500 hover:bg-white/[.05] hover:text-white"><GitPullRequest className="size-4" /></button><div className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-teal-300 to-blue-500 text-xs font-bold text-slate-950">DV</div></div>
        </header>
        <main className="grid-fade min-h-[calc(100vh-68px)]">{children}</main>
      </div>
    </div>
  );
}