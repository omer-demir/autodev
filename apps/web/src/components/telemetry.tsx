"use client";

import { useEffect } from "react";
import { useReportWebVitals } from "next/web-vitals";

import { initializeBrowserTracing } from "@/lib/browser-telemetry";

type ClientMetric = {
  name: string;
  value: number;
  rating?: string;
};

function recordClientMetric(metric: ClientMetric) {
  const body = JSON.stringify(metric);
  if (!navigator.sendBeacon?.("/api/telemetry/metrics", new Blob([body], { type: "application/json" }))) {
    void fetch("/api/telemetry/metrics", {
      method: "POST",
      body,
      headers: { "content-type": "application/json" },
      keepalive: true,
    });
  }
}

export function Telemetry() {
  useReportWebVitals((metric) => {
    recordClientMetric({
      name: metric.name,
      value: metric.value,
      rating: metric.rating,
    });
  });

  useEffect(() => {
    void initializeBrowserTracing();

    const onError = () => {
      recordClientMetric({ name: "client_error", value: 1 });
    };
    const onUnhandledRejection = () => {
      recordClientMetric({ name: "unhandled_rejection", value: 1 });
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, []);

  return null;
}
