"use client";

import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { api } from "@/lib/api";

export function SandboxTerminal({ sandboxId }: { sandboxId: string }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!host.current) return;
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "var(--font-geist-mono), monospace",
      fontSize: 13,
      theme: { background: "#090d13", foreground: "#cbd5e1", cursor: "#5eead4", green: "#5eead4" },
      rows: 18,
    });
    term.open(host.current);
    term.writeln("\x1b[1;36mAgentic SDLC sandbox\x1b[0m");
    term.writeln("Connected to sandbox — NOT the host terminal\r\n");
    let line = "";
    const prompt = () => term.write("\r\n\x1b[32msandbox\x1b[0m:\x1b[34m/workspace/project\x1b[0m$ ");
    prompt();
    const disposable = term.onData(async (data) => {
      if (data === "\r") {
        const command = line.trim(); line = "";
        if (!command) { prompt(); return; }
        term.write("\r\n");
        try {
          const result = await api.execute(sandboxId, command);
          term.writeln(result.output.replaceAll("\n", "\r\n"));
        } catch { term.writeln("\x1b[31mCommand failed: sandbox is unavailable\x1b[0m"); }
        prompt();
      } else if (data === "\u007F") {
        if (line.length) { line = line.slice(0, -1); term.write("\b \b"); }
      } else if (data >= " ") { line += data; term.write(data); }
    });
    return () => { disposable.dispose(); term.dispose(); };
  }, [sandboxId]);
  return <div ref={host} className="h-[360px] overflow-hidden rounded-b-xl bg-[#090d13] p-3" />;
}