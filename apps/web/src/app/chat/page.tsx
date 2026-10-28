"use client";

import { ChangeEvent, FormEvent, Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity, ArrowUpRight, Bot, Check, ChevronDown, ImagePlus, LoaderCircle, MessageSquarePlus, Mic, Send, Sparkles, Square, X } from "lucide-react";
import { Shell } from "@/components/shell";
import { ChatMarkdown } from "@/components/chat-markdown";
import { API_URL, api, describeApiError } from "@/lib/api";
import type { ChatAttachment, ChatMessage, ChatOptions, ChatSession, ChatSessionSummary, Project, RuntimeStatus, TimelineEvent } from "@/lib/types";

const terminal = new Set(["DONE", "FAILED", "CANCELLED"]);

export default function ChatPage() {
  return <Suspense fallback={<Shell><div className="p-8 text-sm text-slate-500">Loading chat…</div></Shell>}><ChatWorkspace /></Suspense>;
}

function ChatWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session");
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [agents, setAgents] = useState<ChatOptions["agents"]>([]);
  const [skills, setSkills] = useState<ChatOptions["skills"]>([]);
  const [models, setModels] = useState<ChatOptions["models"]>([]);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [modelName, setModelName] = useState("");
  const [modelProvider, setModelProvider] = useState("");
  const [draft, setDraft] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [acceptedTurn, setAcceptedTurn] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);

  const loadSessions = useCallback(async () => {
    const result = await api.chatSessions();
    setSessions(result);
    return result;
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.projects(), api.chatOptions(), api.runtime(), api.chatSessions(),
    ]).then(([projectList, options, runtimeStatus, sessionList]) => {
      if (!active) return;
      setProjects(projectList);
      setAgents(options.agents);
      setSkills(options.skills);
      setModels(options.models);
      setRuntime(runtimeStatus);
      setSessions(sessionList);
      const defaultModel = options.models.find((model) => model.name === "auto") || options.models[0];
      setModelName((current) => current || defaultModel?.name || runtimeStatus.configured_model || "");
      setModelProvider((current) => current || defaultModel?.provider || runtimeStatus.active_model_provider);
      setError("");
    }).catch((cause) => { if (active) setError(describeApiError(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!sessionId) {
      return () => { active = false; };
    }
    void api.chatSession(sessionId).then((value) => {
      if (!active) return;
      setSession(value);
      setSelectedProject(value.chat.project_id === null ? "" : String(value.chat.project_id));
      setSelectedAgents(value.chat.agent_ids.map(agentId => agentId.replace(/^did:local:/, "")));
      setSelectedSkills(value.chat.skill_ids);
      setModelName(value.chat.model_name || "");
      setModelProvider(value.chat.model_provider || "");
      setError("");
    }).catch((cause) => { if (active) setError(describeApiError(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sessionId]);

  const activeChatId = session?.chat.id;
  const activeChatStatus = session?.task?.status;
  const lastMessageContent = session?.messages.at(-1)?.content;
  useEffect(() => {
    if (!activeChatId || !activeChatStatus || (terminal.has(activeChatStatus) && !acceptedTurn)) return;
    const timer = window.setInterval(() => {
      void api.chatSession(activeChatId).then((value) => {
        setSession(value);
        if (value.task && terminal.has(value.task.status)) setAcceptedTurn(false);
        setError("");
      }).catch((cause) => setError(describeApiError(cause)));
      void loadSessions().catch((cause) => setError(describeApiError(cause)));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeChatId, activeChatStatus, acceptedTurn, loadSessions]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [
    session?.messages.length,
    session?.events.length,
    lastMessageContent,
  ]);

  function toggle(value: string, values: string[], setValues: (next: string[]) => void) {
    setValues(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  const createModelOptions = selectedProject
    ? models.filter((model) => model.provider === runtime?.model_provider)
    : models;
  const currentModelKey = `${modelProvider}:${modelName}`;
  const selectableModel = createModelOptions.find(
    (model) => `${model.provider}:${model.name}` === currentModelKey,
  ) || createModelOptions[0];

  function chooseProject(value: string) {
    setSelectedProject(value);
    if (value) {
      const taskModel = models.find(
        (model) => model.provider === runtime?.model_provider,
      );
      if (taskModel) {
        setModelName(taskModel.name);
        setModelProvider(taskModel.provider);
      }
    }
  }

  function chooseModel(value: string) {
    const selected = models.find(
      (model) => `${model.provider}:${model.name}` === value,
    );
    if (selected) {
      setModelName(selected.name);
      setModelProvider(selected.provider);
    }
  }

  function appendAssistantDelta(chatId: string, messageId: number, text: string) {
    setSession((current) => {
      if (!current || current.chat.id !== chatId) return current;
      const existing = current.messages.some((message) => message.id === messageId);
      return {
        ...current,
        messages: existing
          ? current.messages.map((message) => message.id === messageId
            ? { ...message, content: message.content + text }
            : message)
          : [...current.messages, {
            id: messageId,
            task_id: current.chat.id,
            role: "assistant",
            content: text,
            created_at: new Date().toISOString(),
            attachments: [],
          }],
      };
    });
  }

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    const supported = new Set([
      "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
      "audio/flac", "audio/mp3", "audio/mpeg", "audio/mp4", "audio/ogg",
      "audio/wav", "audio/webm", "audio/x-wav",
    ]);
    if (files.some((file) => !supported.has(file.type))) {
      setError("Choose a PNG, JPEG, WebP, GIF, PDF, or supported audio file.");
      event.target.value = "";
      return;
    }
    if (files.some((file) => file.size > 10 * 1024 * 1024)) {
      setError("Each attachment must be 10 MiB or smaller.");
      event.target.value = "";
      return;
    }
    if (pendingFiles.length + files.length > 4) {
      setError("Attach no more than four files to a message.");
      event.target.value = "";
      return;
    }
    if ([...pendingFiles, ...files].reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024) {
      setError("Attachments must total 20 MiB or less.");
      event.target.value = "";
      return;
    }
    setPendingFiles([...pendingFiles, ...files]);
    event.target.value = "";
    if (files.every((file) => supported.has(file.type) && file.size <= 10 * 1024 * 1024)) {
      setError("");
    }
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported by this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordingChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) recordingChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(recordingChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setTranscribing(true);
        setBusy(true);
        setError("");
        try {
          const file = await convertRecordingToWav(blob);
          const encoded = await encodeAttachment(file);
          const result = await api.transcribeChatAudio(
            encoded,
            modelName || session?.chat.model_name || "auto",
            modelProvider || session?.chat.model_provider || runtime?.active_model_provider || "",
          );
          setDraft((current) => [current.trim(), result.transcript].filter(Boolean).join(" "));
        } catch (cause) {
          setError(describeApiError(cause));
        } finally {
          setTranscribing(false);
          setBusy(false);
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
      setError("");
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }

  async function createSession(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    const submittedFiles = pendingFiles;
    if (!content && !submittedFiles.length) {
      setError("Enter a message or attach a file to start the chat.");
      return;
    }
    if (selectedProject && submittedFiles.length) {
      setError("Remove attachments to start a repository task.");
      return;
    }
    const createdAt = new Date().toISOString();
    const chatId = `pending-${Date.now()}`;
    const optimisticMessage: ChatMessage = {
      id: -Date.now(),
      task_id: chatId,
      role: "user",
      content,
      created_at: createdAt,
      attachments: [],
    };
    const agentIds = selectedAgents.map((id) => `did:local:${id}`);
    const optimisticChat: ChatSessionSummary = {
      id: chatId,
      task_id: chatId,
      title: content.slice(0, 29) || "New conversation",
      status: "PROCESSING",
      project_id: selectedProject ? Number(selectedProject) : null,
      agent_ids: agentIds,
      skill_ids: selectedSkills,
      model_name: modelName || null,
      model_provider: modelProvider || selectableModel?.provider || null,
      approval_strategy: "agent_policy" as const,
      updated_at: createdAt,
    };
    setBusy(true);
    setCreatingSession(true);
    setError("");
    setSession({
      chat: optimisticChat,
      task: null,
      messages: [optimisticMessage],
      events: [],
    });
    setDraft("");
    try {
      const attachments = await encodeAttachments(submittedFiles);
      const requestBody = {
        message: content,
        ...(selectedProject ? { project_id: Number(selectedProject) } : {}),
        ...(agentIds.length ? { agent_ids: agentIds } : {}),
        skill_ids: selectedSkills,
        model_name: modelName || null,
        ...(!selectedProject
          ? { model_provider: modelProvider || selectableModel?.provider || null }
          : {}),
        approval_strategy: "agent_policy" as const,
        attachments,
      };
      const opened = selectedProject
        ? await api.createChatSession(requestBody).then((created) =>
          api.chatSession(created.chat.id))
        : await api.createChatSessionStreaming(
          requestBody,
          (delta) => appendAssistantDelta(chatId, optimisticMessage.id - 1, delta),
        );
      setSession(opened);
      setAcceptedTurn(Boolean(opened.task));
      setError(opened.error || "");
      setPendingFiles((current) =>
        current.filter((file) => !submittedFiles.includes(file)),
      );
      router.replace(`/chat?session=${encodeURIComponent(opened.chat.id)}`);
      void loadSessions().catch((cause) => setError(describeApiError(cause)));
    } catch (cause) {
      setSession(null);
      setDraft((current) => current || content);
      setError(describeApiError(cause));
    } finally {
      setBusy(false);
      setCreatingSession(false);
    }
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!session || (!content && !pendingFiles.length) || busy) return;
    const currentSession = session;
    const submittedFiles = pendingFiles;
    const optimisticId = -Date.now();
    const optimisticMessage: ChatMessage = {
      id: optimisticId,
      task_id: currentSession.chat.task_id,
      role: "user",
      content,
      created_at: new Date().toISOString(),
      attachments: [],
    };
    setBusy(true);
    setError("");
    setDraft("");
    setSession((current) => current && current.chat.id === currentSession.chat.id
      ? { ...current, messages: [...current.messages, optimisticMessage] }
      : current);
    let accepted = false;
    try {
      const attachments = await encodeAttachments(submittedFiles);
      const opened = currentSession.task
        ? await api.sendChatMessage(
          currentSession.chat.id, content, attachments,
        ).then(() => api.chatSession(currentSession.chat.id))
        : await api.sendChatMessageStreaming(
          currentSession.chat.id,
          content,
          attachments,
          (delta) => appendAssistantDelta(
            currentSession.chat.id, optimisticId - 1, delta,
          ),
          { model_name: modelName || null, model_provider: modelProvider || null },
        );
      accepted = true;
      setAcceptedTurn(Boolean(opened.task));
      setSession(opened);
      setError(opened.error || "");
      setPendingFiles((current) =>
        current.filter((file) => !submittedFiles.includes(file)),
      );
      await loadSessions();
    } catch (cause) {
      if (!accepted) {
        setDraft((current) => current || content);
        setSession((current) => current && current.chat.id === currentSession.chat.id
          ? {
            ...current,
            messages: current.messages.filter(
              (message) => message.id !== optimisticId,
            ),
          }
          : current);
      }
      setError(describeApiError(cause));
      try {
        setSession(await api.chatSession(currentSession.chat.id));
        if (accepted) {
          setPendingFiles((current) =>
            current.filter((file) => !submittedFiles.includes(file)),
          );
        }
        await loadSessions();
      } catch {
        // Keep the original send error visible; a refresh can recover the saved history.
      }
    } finally {
      setBusy(false);
    }
  }

  function startNewChat() {
    setSession(null);
    setSelectedProject("");
    setSelectedSkills([]);
    setSelectedAgents([]);
    setModelName(models.find((model) => model.name === "auto")?.name || models[0]?.name || runtime?.configured_model || "");
    setAcceptedTurn(false);
    setDraft("");
    setPendingFiles([]);
    setError("");
    router.replace("/chat");
  }

  return <Shell>
    <div className="mx-auto flex h-[calc(100vh-68px)] max-w-[1600px] flex-col p-4 lg:p-6">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div><p className="text-xs font-medium text-teal-300">AUTODEV CHAT</p><h1 className="mt-1 text-2xl font-semibold">Chat</h1><p className="mt-1 text-xs text-slate-500">Ask questions without a repository, or select a repository to start a governed task.</p></div>
        <button onClick={startNewChat} className="inline-flex items-center gap-2 rounded-lg bg-teal-300 px-3 py-2 text-sm font-semibold text-slate-950"><MessageSquarePlus className="size-4" />New chat</button>
      </header>
      {error && <div role="alert" className="mb-3 rounded-lg border border-red-400/20 bg-red-400/5 px-3 py-2 text-xs text-red-200">{error}</div>}
      <div className="grid min-h-0 flex-1 overflow-hidden rounded-xl border border-white/[.07] bg-[#0d121b]/90 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="hidden min-h-0 flex-col border-r border-white/[.07] lg:flex">
          <div className="border-b border-white/[.07] px-4 py-3"><h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent chats</h2></div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
            {sessions.map((item) => <button key={item.id} onClick={() => { setLoading(true); router.replace(`/chat?session=${encodeURIComponent(item.id)}`); }} className={`w-full rounded-lg px-3 py-3 text-left ${session?.chat.id === item.id ? "bg-teal-300/[.07] text-white" : "text-slate-400 hover:bg-white/[.035]"}`}><span className="block truncate text-sm">{item.title || "New conversation"}</span><span className="mt-1 block truncate text-[10px] text-slate-600">{item.agent_ids.length ? item.agent_ids.map(agentLabel).join(", ") : "AutoDev Chat"} · {formatDate(item.updated_at)}</span></button>)}
            {!sessions.length && !loading && <p className="px-3 py-8 text-center text-xs text-slate-600">Your saved chats will appear here.</p>}
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-col">
          {!sessionId && !session ? <form onSubmit={createSession} className="flex min-h-0 flex-1 flex-col overflow-y-auto p-5 lg:p-8">
            <div className="mx-auto my-auto w-full max-w-3xl">
              <div className="mb-7 text-center"><div className="mx-auto grid size-12 place-items-center rounded-2xl border border-teal-300/15 bg-teal-300/[.05]"><Sparkles className="size-5 text-teal-300" /></div><h2 className="mt-4 text-xl font-semibold">What would you like to ask?</h2><p className="mt-2 text-sm text-slate-500">Start chatting now. Add a repository only when you want AutoDev to work on its files.</p></div>
              <label className="sr-only" htmlFor="new-chat-message">Message</label>
              <textarea id="new-chat-message" value={draft} onChange={(event) => setDraft(event.target.value)} rows={4} placeholder="Ask anything…" className="w-full resize-y rounded-xl border border-white/[.09] bg-black/20 px-4 py-3 text-sm leading-6 outline-none focus:border-teal-300/30" />
              <PendingAttachments files={pendingFiles} onRemove={(index) => setPendingFiles((current) => current.filter((_, item) => item !== index))} />
              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <label className={`grid size-10 cursor-pointer place-items-center rounded-lg border border-white/[.08] text-slate-400 hover:bg-white/[.04] ${selectedProject ? "cursor-not-allowed opacity-40" : ""}`} title={selectedProject ? "Attachments are for repository-free chats" : "Attach photos or files"}>
                    <ImagePlus className="size-4" />
                    <input type="file" accept="image/png,image/jpeg,image/webp,image/gif,audio/*,application/pdf" multiple hidden disabled={Boolean(selectedProject)} onChange={addFiles} />
                  </label>
                  <button type="button" onClick={() => void toggleRecording()} disabled={busy} aria-label={recording ? "Stop recording" : "Record voice"} title={recording ? "Stop recording" : "Record voice"} className={`grid size-10 place-items-center rounded-lg border border-white/[.08] text-slate-400 hover:bg-white/[.04] disabled:opacity-40 ${recording ? "text-red-300" : ""}`}>{recording ? <Square className="size-4 fill-current" /> : <Mic className="size-4" />}</button>
                  {transcribing && <span className="text-xs text-slate-500">Transcribing…</span>}
                </div>
                <button disabled={busy || (!draft.trim() && !pendingFiles.length)} className="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-300 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-40">{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}Start chat</button>
              </div>
              <details className="mt-6 rounded-lg border border-white/[.07] bg-black/10 px-4 py-3">
                <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-slate-300"><ChevronDown className="size-4" />Advanced options</summary>
                <div className="mt-4">
                  <label className="block text-xs text-slate-400">Repository (optional)<span className="relative mt-2 block"><select value={selectedProject} onChange={(event) => chooseProject(event.target.value)} className="w-full appearance-none rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 pr-8 text-sm text-slate-200"><option value="">No repository · chatbot mode</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.source_type}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3 size-4 text-slate-500" /></span></label>
                  <label className="mt-4 block text-xs text-slate-400">Model<span className="relative mt-2 block"><select value={selectableModel ? `${selectableModel.provider}:${selectableModel.name}` : ""} onChange={(event) => chooseModel(event.target.value)} className="w-full appearance-none rounded-lg border border-white/[.09] bg-black/20 px-3 py-2.5 pr-8 text-sm text-slate-200">{!createModelOptions.some((model) => `${model.provider}:${model.name}` === currentModelKey) && modelName && <option value={currentModelKey}>{modelName} · {modelProvider || "unavailable"}</option>}{createModelOptions.map((model) => <option key={`${model.provider}:${model.name}`} value={`${model.provider}:${model.name}`}>{model.name} · {model.provider}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-3 size-4 text-slate-500" /></span></label>
                  <ChoiceGroup title="Agents" detail="Optional agent instructions for chatbot mode; repository chats use the selected agents to process a task." empty="No runnable agents are available." options={agents.map((agent) => ({ id: agent.id, label: agent.name || agent.id, detail: agent.description }))} selected={selectedAgents} onToggle={(id) => toggle(id, selectedAgents, setSelectedAgents)} />
                  <ChoiceGroup title="Skills" detail="Optional skills to include in the chatbot context." empty="No imported skills yet. Import skills from Agents & tools." options={skills.map((skill) => ({ id: skill.id, label: skill.name || skill.id, detail: skill.description }))} selected={selectedSkills} onToggle={(id) => toggle(id, selectedSkills, setSelectedSkills)} />
                  <div className="mt-5 rounded-lg border border-white/[.07] bg-black/10 p-3"><p className="text-xs font-medium text-slate-300">Approval strategy</p><p className="mt-1 text-xs leading-5 text-slate-600">Repository tasks follow the selected agents’ governance policies. Chatbot mode does not modify a repository.</p></div>
                </div>
              </details>
            </div>
          </form> : session ? <>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[.07] px-4 py-3 lg:px-6"><div className="min-w-0"><h2 className="truncate text-sm font-medium">{session.chat.title || "Conversation"}</h2><p className="mt-1 truncate text-[10px] text-slate-500">{session.chat.project_id === null ? "No repository · chatbot" : projects.find((project) => project.id === session.chat.project_id)?.name || "Repository"}{session.chat.agent_ids.length ? ` · ${session.chat.agent_ids.map(agentLabel).join(", ")}` : ""}{session.chat.model_provider ? ` · ${session.chat.model_provider}` : ""}{session.chat.model_name ? ` · ${session.chat.model_name}` : ""} · {session.task?.status || session.chat.status}</p></div><div className="flex flex-wrap items-center gap-2"><div className="flex flex-wrap gap-1">{session.chat.skill_ids.map((id) => <span key={id} className="rounded-full border border-white/[.07] px-2 py-1 text-[10px] text-slate-500">{skillLabel(id)}</span>)}</div>{session.chat.project_id !== null && !creatingSession && <Link href={`/tasks/${session.chat.task_id}`} className="inline-flex items-center gap-1 rounded-lg border border-white/[.08] px-2 py-1.5 text-[10px] text-slate-400 hover:text-white">Task details <ArrowUpRight className="size-3" /></Link>}</div></div>
            {session.task?.status === "AWAITING_APPROVAL" && <div className="flex items-center justify-between border-b border-amber-300/15 bg-amber-300/[.035] px-4 py-2 text-xs text-amber-200 lg:px-6"><span>Agent action requires approval before this chat can continue.</span><a href="/governance" className="underline underline-offset-2">Review approvals</a></div>}
            <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5 lg:px-8">
              {session.messages.map((message) => <article key={message.id} className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}>
                {message.role === "assistant" && <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg border border-teal-300/15 bg-teal-300/[.05]"><Bot className="size-4 text-teal-300" /></div>}
                <div className={`max-w-[85%] rounded-xl px-4 py-3 ${message.role === "user" ? "bg-white/[.06]" : "border border-white/[.05] bg-black/10"}`}><div className="mb-1.5 flex items-center gap-2 text-[10px] text-slate-500"><span>{message.role === "user" ? "You" : "AutoDev"}</span><span>·</span><time>{formatDate(message.created_at)}</time></div>{message.content && (message.role === "assistant" ? <ChatMarkdown content={message.content} /> : <p className="whitespace-pre-wrap text-sm leading-6 text-slate-200">{message.content}</p>)}<MessageAttachments attachments={message.attachments || []} />{message.role === "assistant" && <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 border-t border-white/[.05] pt-2 text-[10px] text-slate-500"><span>{message.model_provider || session.chat.model_provider || "Model"} · {message.model_name || session.chat.model_name || "unknown"}</span><span>{typeof message.input_tokens === "number" && typeof message.output_tokens === "number" ? `${message.input_tokens.toLocaleString()} input · ${message.output_tokens.toLocaleString()} output tokens` : "Token usage unavailable"}</span><span title={message.cost_note || undefined}>{formatChatCost(message.estimated_cost_usd)}</span></div>}</div>
              </article>)}
              <ChatActivity events={session.events} />
              {busy && (!session.task || terminal.has(session.task.status)) && <div className="flex items-center gap-3 text-xs text-slate-500"><LoaderCircle className="size-4 animate-spin text-teal-300" />AutoDev is responding…</div>}
              {session.task && !terminal.has(session.task.status) && session.task.status !== "AWAITING_APPROVAL" && <div className="flex items-center gap-3 text-xs text-slate-500"><LoaderCircle className="size-4 animate-spin text-teal-300" />Agents are working with the selected context…</div>}
              {(session.error || session.task?.status === "FAILED") && <div role="alert" className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs text-red-200">{session.error || session.events.find((event) => event.type === "task.failed")?.detail || "The agent run failed. Review the task timeline for details."}</div>}
              {!session.messages.length && <div className="grid h-full place-items-center text-center"><div><MessageSquarePlus className="mx-auto size-6 text-slate-700" /><p className="mt-3 text-sm text-slate-500">Send a message to begin.</p></div></div>}
            </div>
            <form onSubmit={sendMessage} className="border-t border-white/[.07] p-3 lg:px-6 lg:py-4">
              {!session.task && models.length > 0 && <label className="mx-auto mb-2 block max-w-4xl text-[10px] text-slate-500">Model for this message<span className="relative mt-1 block"><select value={currentModelKey} onChange={(event) => chooseModel(event.target.value)} disabled={busy} className="w-full appearance-none rounded-lg border border-white/[.08] bg-black/20 px-3 py-2 pr-8 text-xs text-slate-300 disabled:opacity-50">{!models.some((model) => `${model.provider}:${model.name}` === currentModelKey) && modelName && <option value={currentModelKey}>{modelName} · {modelProvider || "unavailable"}</option>}{models.map((model) => <option key={`${model.provider}:${model.name}`} value={`${model.provider}:${model.name}`}>{model.name} · {model.provider}</option>)}</select><ChevronDown className="pointer-events-none absolute right-3 top-2 size-3.5 text-slate-500" /></span></label>}
              <div className="mx-auto max-w-4xl rounded-xl border border-white/[.09] bg-black/20 p-2 focus-within:border-teal-300/25">
                <PendingAttachments files={pendingFiles} onRemove={(index) => setPendingFiles((current) => current.filter((_, item) => item !== index))} />
                <div className="flex items-end gap-2">
                  <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} disabled={busy || Boolean(session.task && (!terminal.has(session.task.status) || session.task.status === "AWAITING_APPROVAL"))} rows={2} placeholder={session.task?.status === "AWAITING_APPROVAL" ? "Approve or deny the pending action to continue…" : session.task && !terminal.has(session.task.status) ? "Agents are working…" : "Message AutoDev…"} className="max-h-40 min-h-12 flex-1 resize-y bg-transparent px-2 py-2 text-sm leading-5 outline-none placeholder:text-slate-600 disabled:opacity-50" />
                  <div className="flex shrink-0 items-center gap-1">
                    {!session.task && <label className="grid size-9 cursor-pointer place-items-center rounded-lg text-slate-400 hover:bg-white/[.04]" title="Attach photos or files"><ImagePlus className="size-4" /><input type="file" accept="image/png,image/jpeg,image/webp,image/gif,audio/*,application/pdf" multiple hidden onChange={addFiles} /></label>}
                    <button type="button" onClick={() => void toggleRecording()} disabled={busy} aria-label={recording ? "Stop recording" : "Record voice"} title={recording ? "Stop recording" : "Record voice"} className={`grid size-9 place-items-center rounded-lg text-slate-400 hover:bg-white/[.04] disabled:opacity-40 ${recording ? "text-red-300" : ""}`}>{recording ? <Square className="size-4 fill-current" /> : <Mic className="size-4" />}</button>
                    <button aria-label="Send message" disabled={busy || Boolean(session.task && (!terminal.has(session.task.status) || session.task.status === "AWAITING_APPROVAL")) || (!draft.trim() && !pendingFiles.length)} className="grid size-9 shrink-0 place-items-center rounded-lg bg-teal-300 text-slate-950 disabled:opacity-40">{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}</button>
                  </div>
                </div>
              </div>
              {transcribing && <p className="mx-auto mt-2 max-w-4xl text-[10px] text-teal-300">Transcribing your recording…</p>}
              <p className="mx-auto mt-2 max-w-4xl text-[10px] text-slate-600">Enter to send · Shift+Enter for a new line. {session.task ? "Repository writes follow the selected agents’ governance policies." : "This chat does not create or modify a task."}</p>
            </form>
          </> : <div className="grid flex-1 place-items-center text-sm text-slate-500">{loading ? "Loading chat…" : "Chat not found."}</div>}
        </section>
      </div>
    </div>
  </Shell>;

  function agentLabel(id: string) {
    const key = id.replace(/^did:local:/, "");
    const agent = agents.find((item) => item.id === key);
    return String(agent?.name || key || "Agent");
  }

  function skillLabel(id: string) {
    return String(skills.find((item) => item.id === id)?.name || id);
  }
}

function ChatActivity({ events }: { events: TimelineEvent[] }) {
  const items = events.flatMap((event) => {
    const message = chatActivityMessage(event);
    return message ? [{ event, message }] : [];
  }).slice(-30);
  if (!items.length) return null;
  return <section aria-label="Agent progress" className="ml-10 max-w-2xl rounded-xl border border-white/[.06] bg-black/10 p-4">
    <h3 className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-300"><Activity className="size-3.5 text-teal-300" />Agent progress and actions</h3>
    <ol className="space-y-2.5">
      {items.map(({ event, message }) => <li key={event.id} className="flex items-start gap-2.5 text-xs">
        <span className={`mt-1 size-1.5 shrink-0 rounded-full ${event.severity === "error" ? "bg-red-300" : event.severity === "warning" ? "bg-amber-300" : "bg-teal-300/70"}`} />
        <span className="min-w-0 flex-1 text-slate-400">{message}</span>
        <time className="shrink-0 text-[10px] text-slate-600">{formatDate(event.created_at)}</time>
      </li>)}
    </ol>
  </section>;
}

function chatActivityMessage(event: TimelineEvent): string | null {
  const capability = typeof event.data?.capability === "string" ? event.data.capability : "";
  switch (event.type) {
    case "agent.started": return `Agent started · ${event.detail}`;
    case "workflow.stage_started": return `Agent stage started · ${String(event.data?.stage_id || "collaboration")}`;
    case "model.call": return `Model request · ${event.detail}`;
    case "model.error": return "Model provider reported an error.";
    case "tool.requested": return `Calling ${event.title} · ${typeof event.data?.attempt === "string" ? event.data.attempt : "request sent"}`;
    case "tool.completed": return `Completed tool · ${event.title}${capability ? ` (${capability})` : ""}`;
    case "tool.denied": return `Tool blocked · ${typeof event.data?.tool === "string" ? event.data.tool : capability || event.title}: ${typeof event.data?.attempt === "string" ? event.data.attempt : "governance denied the request"}`;
    case "runtime_supervision.denied": return `Action blocked by runtime supervision · ${capability || "policy"}`;
    case "repository.materializing": return "Preparing repository workspace.";
    case "repository.ready": return "Repository workspace is ready.";
    case "file.modified": return `Repository changes collected · ${event.detail}`;
    case "test.completed": return "Test run completed.";
    case "security.completed": return "Security checks completed.";
    case "approval.created": return event.title;
    case "approval.approved": return "Approval granted.";
    case "approval.denied": return "Approval denied.";
    case "task.completed": return "Task completed.";
    case "task.failed": return "Agent run failed. Review task details for the error.";
    default: return null;
  }
}

function formatChatCost(value: number | null | undefined): string {
  if (typeof value !== "number") return "Cost unavailable";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 8,
  }).format(value);
}

function ChoiceGroup({ title, detail, empty, options, selected, onToggle }: {
  title: string; detail: string; empty: string;
  options: { id: string; label: string; detail: string }[];
  selected: string[]; onToggle: (id: string) => void;
}) {
  return <section className="mt-5">
    <div className="flex items-end justify-between gap-3"><div><h3 className="text-xs font-medium text-slate-300">{title}</h3><p className="mt-1 text-[10px] leading-4 text-slate-600">{detail}</p></div><span className="text-[10px] text-slate-600">{selected.length} selected</span></div>
    <div className="mt-2 max-h-36 space-y-1 overflow-y-auto rounded-lg border border-white/[.07] p-1.5">
      {options.map((option) => <button type="button" key={option.id} onClick={() => onToggle(option.id)} className="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left hover:bg-white/[.035]"><span className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded border ${selected.includes(option.id) ? "border-teal-300 bg-teal-300 text-slate-950" : "border-white/15"}`}>{selected.includes(option.id) && <Check className="size-3" />}</span><span className="min-w-0"><span className="block truncate text-xs text-slate-300">{option.label}</span><span className="mt-0.5 block truncate text-[10px] text-slate-600">{option.detail}</span></span></button>)}
      {!options.length && <p className="p-3 text-center text-[10px] text-slate-600">{empty}</p>}
    </div>
  </section>;
}

function PendingAttachments({ files, onRemove }: {
  files: File[];
  onRemove: (index: number) => void;
}) {
  if (!files.length) return null;
  return <ul className="mb-2 flex flex-wrap gap-2">
    {files.map((file, index) => <li key={`${file.name}:${index}`} className="flex items-center gap-2 rounded-lg border border-white/[.08] px-2 py-1 text-[10px] text-slate-400">
      <span className="max-w-48 truncate">{file.name}</span>
      <button type="button" onClick={() => onRemove(index)} aria-label={`Remove ${file.name}`} className="text-slate-500 hover:text-white"><X className="size-3" /></button>
    </li>)}
  </ul>;
}

function MessageAttachments({ attachments }: { attachments: ChatAttachment[] }) {
  if (!attachments.length) return null;
  return <div className="mt-3 space-y-2">
    {attachments.map((attachment) => {
      const url = `${API_URL}${attachment.url}`;
      if (attachment.media_type.startsWith("image/")) {
        return <a key={attachment.id} href={url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg">
          <Image src={url} alt={attachment.name} width={560} height={420} unoptimized className="max-h-80 w-auto max-w-full object-contain" />
        </a>;
      }
      if (attachment.media_type.startsWith("audio/")) {
        return <div key={attachment.id} className="min-w-56">
          <audio controls src={url} className="max-w-full" />
          <p className="mt-1 text-[10px] text-slate-500">{attachment.name}</p>
        </div>;
      }
      return <a key={attachment.id} href={url} download={attachment.name} className="inline-flex max-w-full items-center gap-2 rounded-lg border border-white/[.08] px-3 py-2 text-xs text-teal-200 hover:bg-white/[.04]">
        <span className="truncate">{attachment.name}</span>
      </a>;
    })}
  </div>;
}

async function encodeAttachment(file: File) {
  const buffer = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < buffer.length; offset += chunkSize) {
    binary += String.fromCharCode(...buffer.subarray(offset, offset + chunkSize));
  }
  return {
    name: file.name,
    media_type: file.type || "application/octet-stream",
    data: btoa(binary),
  };
}

async function encodeAttachments(files: File[]) {
  return Promise.all(files.map(encodeAttachment));
}

async function convertRecordingToWav(recording: Blob): Promise<File> {
  const context = new AudioContext();
  try {
    const audio = await context.decodeAudioData(await recording.arrayBuffer());
    const samples = new Float32Array(audio.length);
    for (let channel = 0; channel < audio.numberOfChannels; channel += 1) {
      const source = audio.getChannelData(channel);
      for (let index = 0; index < source.length; index += 1) {
        samples[index] += source[index] / audio.numberOfChannels;
      }
    }

    const dataSize = samples.length * 2;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);
    const write = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
      }
    };
    write(0, "RIFF");
    view.setUint32(4, 36 + dataSize, true);
    write(8, "WAVE");
    write(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, audio.sampleRate, true);
    view.setUint32(28, audio.sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, "data");
    view.setUint32(40, dataSize, true);
    for (let index = 0; index < samples.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(44 + index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return new File([buffer], "voice-message.wav", { type: "audio/wav" });
  } finally {
    await context.close();
  }
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
