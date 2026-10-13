import { webMetrics } from "@/lib/metrics";

export const runtime = "nodejs";

const VITALS = new Set(["CLS", "FCP", "FID", "INP", "LCP", "TTFB"]);
const EVENTS = new Set(["client_error", "unhandled_rejection"]);
const RATINGS = new Set(["good", "needs-improvement", "poor"]);

type MetricBody = {
  name?: unknown;
  value?: unknown;
  rating?: unknown;
};

export async function POST(request: Request) {
  let body: MetricBody;
  try {
    body = (await request.json()) as MetricBody;
  } catch {
    return Response.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  if (typeof body.name !== "string" || typeof body.value !== "number" || !Number.isFinite(body.value)) {
    return Response.json({ detail: "Invalid metric" }, { status: 400 });
  }

  if (VITALS.has(body.name)) {
    const rating = typeof body.rating === "string" && RATINGS.has(body.rating) ? body.rating : "unknown";
    webMetrics.webVitals.observe({ name: body.name, rating }, Math.max(0, body.value));
    return new Response(null, { status: 204 });
  }

  if (EVENTS.has(body.name)) {
    webMetrics.clientEvents.inc({ name: body.name, rating: "unknown" });
    return new Response(null, { status: 204 });
  }

  return Response.json({ detail: "Unsupported metric" }, { status: 400 });
}
