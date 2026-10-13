import type { NextConfig } from "next";

const otlpEndpoint = (process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://127.0.0.1:4318")
  .replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.WORKBENCH_API_URL || "http://127.0.0.1:8000"}/api/:path*`,
      },
      {
        source: "/telemetry/v1/traces",
        destination: `${otlpEndpoint}/v1/traces`,
      },
    ];
  },
};

export default nextConfig;
