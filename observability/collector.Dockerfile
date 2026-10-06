FROM otel/opentelemetry-collector-contrib:0.143.0
COPY observability/otel-collector.yaml /etc/otelcol-contrib/autodev.yaml