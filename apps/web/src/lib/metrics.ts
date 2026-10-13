import {
  Counter,
  Histogram,
  Registry,
  collectDefaultMetrics,
} from "prom-client";

const globalMetrics = globalThis as typeof globalThis & {
  autodevWebMetrics?: {
    registry: Registry;
    clientEvents: Counter<"name" | "rating">;
    webVitals: Histogram<"name" | "rating">;
  };
};

function createMetrics() {
  const registry = new Registry();
  registry.setDefaultLabels({ service: "autodev-web" });
  collectDefaultMetrics({ prefix: "autodev_web_", register: registry });

  return {
    registry,
    clientEvents: new Counter({
      name: "autodev_web_client_events_total",
      help: "Privacy-safe client events received by the web service.",
      labelNames: ["name", "rating"],
      registers: [registry],
    }),
    webVitals: new Histogram({
      name: "autodev_web_vital_value",
      help: "Browser Web Vital observations in their native units.",
      labelNames: ["name", "rating"],
      buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 50, 100, 250, 500, 1000, 2500, 5000],
      registers: [registry],
    }),
  };
}

export const webMetrics = (globalMetrics.autodevWebMetrics ??= createMetrics());
