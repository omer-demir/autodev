"use client";

let initialized = false;

function sanitizedUrl(value: string) {
  try {
    const url = new URL(value, window.location.origin);
    return `${url.origin}${url.pathname}`;
  } catch {
    return "unknown";
  }
}

export async function initializeBrowserTracing() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;

  const [
    { ZoneContextManager },
    { DocumentLoadInstrumentation },
    { OTLPTraceExporter },
    { registerInstrumentations },
    { FetchInstrumentation },
    { resourceFromAttributes },
    { BatchSpanProcessor },
    { WebTracerProvider },
  ] = await Promise.all([
    import("@opentelemetry/context-zone"),
    import("@opentelemetry/instrumentation-document-load"),
    import("@opentelemetry/exporter-trace-otlp-http"),
    import("@opentelemetry/instrumentation"),
    import("@opentelemetry/instrumentation-fetch"),
    import("@opentelemetry/resources"),
    import("@opentelemetry/sdk-trace-base"),
    import("@opentelemetry/sdk-trace-web"),
  ]);

  const exporter = new OTLPTraceExporter({ url: "/telemetry/v1/traces" });
  const provider = new WebTracerProvider({
    resource: resourceFromAttributes({
      "service.name": "autodev-web-browser",
      "service.namespace": "autodev",
      "deployment.environment.name": "local",
    }),
    spanProcessors: [new BatchSpanProcessor(exporter)],
  });
  provider.register({ contextManager: new ZoneContextManager() });

  registerInstrumentations({
    instrumentations: [
      new DocumentLoadInstrumentation(),
      new FetchInstrumentation({
        clearTimingResources: true,
        ignoreUrls: [/\/telemetry\//],
        propagateTraceHeaderCorsUrls: [
          /^\/api\//,
          /^http:\/\/localhost:8000\//,
          /^http:\/\/127\.0\.0\.1:8000\//,
        ],
        applyCustomAttributesOnSpan(span, request) {
          const url = sanitizedUrl(request instanceof Request ? request.url : "unknown");
          span.setAttribute("url.full", url);
          span.setAttribute("http.url", url);
        },
      }),
    ],
  });
}
