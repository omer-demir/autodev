"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ArrowUpRight, CheckCircle2, Clock3, ListTodo, XCircle } from "lucide-react";
import { Shell } from "@/components/shell";
import { api, describeApiError } from "@/lib/api";
import type { Task } from "@/lib/types";

const terminal = new Set(["DONE", "FAILED", "CANCELLED"]);

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState("ALL");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setTasks(await api.tasks()); setError(""); }
    catch (cause) { setError(describeApiError(cause)); }
  }, []);
  useEffect(() => { const initial = setTimeout(() => void load(), 0); const timer = setInterval(() => void load(), 5000); return () => { clearTimeout(initial); clearInterval(timer); }; }, [load]);
  const visible = useMemo(() => tasks.filter((task) => filter === "ALL" || (filter === "ACTIVE" ? !terminal.has(task.status) : task.status === filter)), [tasks, filter]);
  const stats = { active: tasks.filter((task) => !terminal.has(task.status)).length, approval: tasks.filter((task) => task.status === "AWAITING_APPROVAL").length, done: tasks.filter((task) => task.status === "DONE").length, failed: tasks.filter((task) => task.status === "FAILED").length };
  return <Shell><div className="mx-auto max-w-7xl p-5 lg:p-8">
    <Header eyebrow="WORKSPACE" title="Tasks" description="Inspect every governed run, its current lifecycle phase, progress, and durable task detail." />
    {error && <ErrorBanner text={error} />}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Stat icon={Activity} label="Active" value={stats.active} tone="text-blue-300" /><Stat icon={Clock3} label="Awaiting approval" value={stats.approval} tone="text-amber-300" /><Stat icon={CheckCircle2} label="Completed" value={stats.done} tone="text-emerald-300" /><Stat icon={XCircle} label="Failed" value={stats.failed} tone="text-red-300" /></div>
    <div className="mt-6 flex flex-wrap gap-2">{["ALL", "ACTIVE", "AWAITING_APPROVAL", "DONE", "FAILED", "CANCELLED"].map((item) => <button key={item} onClick={() => setFilter(item)} className={`rounded-lg border px-3 py-2 text-xs ${filter === item ? "border-teal-300/30 bg-teal-300/10 text-teal-200" : "border-white/[.07] text-slate-500"}`}>{item.replaceAll("_", " ")}</button>)}</div>
    <section className="mt-4 overflow-hidden rounded-xl border border-white/[.07] bg-[#0d121b]">
      <div className="grid grid-cols-[110px_1fr_150px_110px_28px] gap-3 border-b border-white/[.06] px-5 py-3 text-[10px] uppercase tracking-wider text-slate-600"><span>Task</span><span>Work</span><span>Phase</span><span>Status</span><span /></div>
      {visible.map((task) => <Link key={task.id} href={`/tasks/${task.id}`} className="grid grid-cols-[110px_1fr_150px_110px_28px] gap-3 border-b border-white/[.05] px-5 py-4 text-xs last:border-0 hover:bg-white/[.025]"><span className="font-mono text-slate-500">{task.id}</span><span><b className="block font-medium text-slate-200">{task.title}</b><span className="mt-2 block h-1 rounded bg-white/[.05]"><span className="block h-1 rounded bg-teal-300" style={{ width: `${task.progress}%` }} /></span></span><span className="text-slate-400">{task.phase}</span><span className={task.status === "FAILED" ? "text-red-300" : task.status === "DONE" ? "text-emerald-300" : "text-amber-200"}>{task.status.replaceAll("_", " ")}</span><ArrowUpRight className="size-4 text-slate-600" /></Link>)}
      {!visible.length && <Empty text="No tasks match this filter." />}
    </section>
  </div></Shell>;
}

function Header({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <div className="mb-7"><p className="text-xs font-medium text-teal-300">{eyebrow}</p><h1 className="mt-1 text-3xl font-semibold">{title}</h1><p className="mt-2 text-sm text-slate-500">{description}</p></div>; }
function Stat({ icon: Icon, label, value, tone }: { icon: typeof Activity; label: string; value: number; tone: string }) { return <div className="rounded-xl border border-white/[.07] bg-[#0d121b] p-5"><Icon className={`size-4 ${tone}`} /><p className="mt-4 text-xs text-slate-600">{label}</p><p className="mt-1 font-mono text-3xl">{value}</p></div>; }
function ErrorBanner({ text }: { text: string }) { return <div className="mb-5 rounded-xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{text}</div>; }
function Empty({ text }: { text: string }) { return <div className="p-12 text-center"><ListTodo className="mx-auto size-6 text-slate-700" /><p className="mt-3 text-sm text-slate-600">{text}</p></div>; }
