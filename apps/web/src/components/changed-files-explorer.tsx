"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  Folder,
  FolderOpen,
  LoaderCircle,
} from "lucide-react";
import { api, describeApiError } from "@/lib/api";
import type { ChangeTreeEntry } from "@/lib/types";

interface ChangedFilesExplorerProps {
  taskId: string;
  revision: string;
  fileCount: number;
  selectedPath: string;
  onSelect: (path: string) => void;
}

export function ChangedFilesExplorer({
  taskId,
  revision,
  fileCount,
  selectedPath,
  onSelect,
}: ChangedFilesExplorerProps) {
  const [directories, setDirectories] = useState<Record<string, ChangeTreeEntry[]>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set([""]));
  const [error, setError] = useState("");
  const inFlight = useRef(new Set<string>());

  const loadDirectory = useCallback(async (path: string) => {
    if (inFlight.current.has(path)) return;
    inFlight.current.add(path);
    setLoading((current) => new Set(current).add(path));
    try {
      const result = await api.taskChanges(taskId, path);
      if (result.revision !== revision) return;
      setDirectories((current) => ({ ...current, [path]: result.entries }));
      setError("");
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      inFlight.current.delete(path);
      setLoading((current) => {
        const next = new Set(current);
        next.delete(path);
        return next;
      });
    }
  }, [revision, taskId]);

  useEffect(() => {
    const initial = window.setTimeout(() => void loadDirectory(""), 0);
    return () => window.clearTimeout(initial);
  }, [loadDirectory]);

  async function toggle(entry: ChangeTreeEntry) {
    if (entry.kind !== "folder") return;
    if (expanded.has(entry.path)) {
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(entry.path);
        return next;
      });
      return;
    }
    setExpanded((current) => new Set(current).add(entry.path));
    if (!directories[entry.path]) await loadDirectory(entry.path);
  }

  return <div>
    <div className="flex items-center justify-between border-b border-white/[.06] px-4 py-3">
      <span className="text-[10px] text-slate-600">{fileCount.toLocaleString()} changed files</span>
      <span className="text-[10px] text-slate-700">Folders load on expand</span>
    </div>
    {error && <div role="alert" className="border-b border-red-400/10 bg-red-400/[.04] px-4 py-3 text-[11px] leading-5 text-red-200">{error}</div>}
    <div className="max-h-[560px] overflow-auto py-1">
      {loading.has("") && !directories[""]
        ? <div className="flex items-center gap-2 px-4 py-4 text-xs text-slate-600"><LoaderCircle className="size-3.5 animate-spin" />Loading root folders…</div>
        : <TreeLevel
            directory=""
            depth={0}
            directories={directories}
            expanded={expanded}
            loading={loading}
            selectedPath={selectedPath}
            onSelect={onSelect}
            onToggle={(entry) => void toggle(entry)}
          />}
    </div>
  </div>;
}

function TreeLevel({
  directory,
  depth,
  directories,
  expanded,
  loading,
  selectedPath,
  onSelect,
  onToggle,
}: {
  directory: string;
  depth: number;
  directories: Record<string, ChangeTreeEntry[]>;
  expanded: Set<string>;
  loading: Set<string>;
  selectedPath: string;
  onSelect: (path: string) => void;
  onToggle: (entry: ChangeTreeEntry) => void;
}) {
  return <>{(directories[directory] ?? []).map((entry) => {
    const folder = entry.kind === "folder";
    const open = folder && expanded.has(entry.path);
    const pending = folder && loading.has(entry.path);
    return <div key={entry.path}>
      <button
        type="button"
        aria-expanded={folder ? open : undefined}
        onClick={() => folder ? onToggle(entry) : onSelect(entry.path)}
        className={`flex w-full items-center gap-1.5 py-2 pr-3 text-left text-xs transition-colors ${selectedPath === entry.path ? "bg-teal-300/[.08] text-teal-200" : "text-slate-400 hover:bg-white/[.03] hover:text-slate-200"}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        {folder
          ? pending
            ? <LoaderCircle className="size-3.5 shrink-0 animate-spin text-slate-600" />
            : open
              ? <ChevronDown className="size-3.5 shrink-0 text-slate-600" />
              : <ChevronRight className="size-3.5 shrink-0 text-slate-600" />
          : <span className="w-3.5 shrink-0" />}
        {folder
          ? open
            ? <FolderOpen className="size-3.5 shrink-0 text-amber-300/80" />
            : <Folder className="size-3.5 shrink-0 text-amber-300/70" />
          : <FileCode2 className="size-3.5 shrink-0 text-blue-300/70" />}
        <span className="min-w-0 flex-1 truncate font-mono" title={entry.path}>{entry.name}</span>
        {folder && <span className="shrink-0 font-mono text-[9px] text-slate-700">{entry.file_count}</span>}
        {!folder && <ChangeStats additions={entry.additions} deletions={entry.deletions} />}
      </button>
      {open && directories[entry.path] && <TreeLevel
        directory={entry.path}
        depth={depth + 1}
        directories={directories}
        expanded={expanded}
        loading={loading}
        selectedPath={selectedPath}
        onSelect={onSelect}
        onToggle={onToggle}
      />}
    </div>;
  })}</>;
}

function ChangeStats({ additions, deletions }: { additions: number; deletions: number }) {
  return <span className="flex shrink-0 gap-1 font-mono text-[9px]">
    <span className="text-emerald-400">+{additions}</span>
    <span className="text-red-400">-{deletions}</span>
  </span>;
}
