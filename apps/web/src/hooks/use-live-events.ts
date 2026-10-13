"use client";

import { useEffect, useRef } from "react";
import { API_URL } from "@/lib/api";

type LiveEvent = { event?: string; task_id?: string };

export function useLiveEvents(onEvent: () => void | Promise<void>, taskId?: string) {
  const callback = useRef(onEvent);
  useEffect(() => { callback.current = onEvent; }, [onEvent]);

  useEffect(() => {
    const path = taskId ? `/api/tasks/${encodeURIComponent(taskId)}/events/ws` : "/api/events/ws";
    const developmentApiOrigin = `${window.location.protocol}//${window.location.hostname}:8000`;
    const origin = process.env.NEXT_PUBLIC_WS_URL || API_URL ||
      (window.location.port === "3000" ? developmentApiOrigin : window.location.origin);
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
    const stopPolling = () => {
      if (polling) clearInterval(polling);
      polling = undefined;
    };
    const startPolling = () => {
      if (!polling && document.visibilityState === "visible") {
        polling = setInterval(refresh, 3000);
      }
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
      socket.onopen = () => { stopPolling(); socket?.send("subscribe"); refresh(); };
      socket.onclose = () => {
        socket = undefined;
        if (!stopped && document.visibilityState === "visible") {
          startPolling();
          retry = setTimeout(connect, 1500);
        }
      };
    };
    const visibilityChanged = () => {
      if (document.visibilityState === "hidden") {
        if (retry) clearTimeout(retry);
        stopPolling();
        socket?.close();
      } else {
        startPolling();
        connect();
        refresh();
      }
    };
    startPolling();
    connect();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      stopPolling();
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", visibilityChanged);
      socket?.close();
    };
  }, [taskId]);
}