FROM grafana/loki:3.5.7
COPY observability/loki.yaml /etc/loki/loki.yaml
