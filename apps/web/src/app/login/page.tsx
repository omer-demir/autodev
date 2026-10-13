import { Hexagon, LogIn } from "lucide-react";

export default function LoginPage() {
  return <main className="grid min-h-screen place-items-center bg-[#080b11] p-5 text-slate-100"><section className="w-full max-w-sm border border-white/[.08] bg-[#0d121b] p-7"><span className="grid size-10 place-items-center bg-teal-300 text-slate-950"><Hexagon className="size-5" /></span><h1 className="mt-6 text-2xl font-semibold">Sign in to Autodev</h1><p className="mt-2 text-sm leading-6 text-slate-500">Use your organization identity to access governed tasks, sessions, and evidence.</p><a href="/api/auth/login" className="mt-7 flex w-full items-center justify-center gap-2 bg-teal-300 px-4 py-3 text-sm font-semibold text-slate-950"><LogIn className="size-4" />Continue with OIDC</a></section></main>;
}
