import { registerOTel } from "@vercel/otel";
import { trace } from "@opentelemetry/api";
import type { Instrumentation } from "next";

export function register() {
  registerOTel({
    serviceName: "autodev-web",
    attributes: {
      "service.namespace": "autodev",
      "deployment.environment.name": process.env.WORKBENCH_EXECUTION_MODE || "local",
    },
    instrumentationConfig: {
      fetch: {
        propagateContextUrls: [
          /^http:\/\/api:8000\//,
          /^http:\/\/localhost:8000\//,
          /^http:\/\/127\.0\.0\.1:8000\//,
        ],
        dontPropagateContextUrls: [/\/telemetry\/v1\/traces$/],
      },
    },
  });
}

export const onRequestError: Instrumentation.onRequestError = (error, _request, context) => {
  const spanContext = trace.getActiveSpan()?.spanContext();
  const errorType = error instanceof Error ? error.name.slice(0, 80) : "UnknownError";
  console.error(JSON.stringify({
    timestamp: new Date().toISOString(),
    severity: "ERROR",
    event: "request_error",
    error_type: errorType,
    route_path: context.routePath,
    route_type: context.routeType,
    router_kind: context.routerKind,
    service_name: "autodev-web",
    ...(spanContext?.traceId
      ? { trace_id: spanContext.traceId, span_id: spanContext.spanId }
      : {}),
  }));
};
