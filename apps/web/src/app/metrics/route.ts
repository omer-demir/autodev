import { webMetrics } from "@/lib/metrics";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return new Response(await webMetrics.registry.metrics(), {
    headers: {
      "content-type": webMetrics.registry.contentType,
      "cache-control": "no-store",
    },
  });
}
