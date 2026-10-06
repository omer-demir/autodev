"use client";

import { useEffect, useRef } from "react";
import { API_URL } from "@/lib/api";

type LiveEvent = { event?: string; task_id?: string };

export function useLiveEvents(onEvent: () => void | Promise<void>, taskId?: string) {
  const callback = useRef(onEvent);
  useEffect(() => { callback.current = onEvent; }, [onEvent]);

  useEffect(() => {
    const path = taskId ? `/api/tasks/${encodeURIComponent(taskId)}/events/ws` : "/api/events/ws";
    const origin = API_URL || window.location.origin;
    const url = origin.replace(/^http/, "ws") + path;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let polling: ReturnType<typeof setInterval> | undefined;
    let stopped = false;
    let refreshing = false;

    const refresh = () => {
      if (refreshing || document.visibilityState === "hidden") return;
      refreshing = true;
      void Promise.resolve(callback.current()).finally(() => { refreshing = false; });
    };
    const connect = () => {
      if (stopped || document.visibilityState === "hidden" ||
          socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
      socket = new WebSocket(url);
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as LiveEvent;
          if (!taskId || event.task_id === taskId) refresh();
        } catch {
          refresh();
        }
      };
      socket.onopen = () => { socket?.send("subscribe"); refresh(); };
      socket.onclose = () => {
        socket = undefined;
        if (!stopped && document.visibilityState === "visible") retry = setTimeout(connect, 1500);
      };
    };
    const visibilityChanged = () => {
      if (document.visibilityState === "hidden") {
        if (retry) clearTimeout(retry);
        socket?.close();
      } else {
        connect();
        refresh();
      }
    };
    connect();
    if (taskId) polling = setInterval(refresh, 3000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      if (polling) clearInterval(polling);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", visibilityChanged);
      socket?.close();
    };
  }, [taskId]);
}