FROM prom/prometheus:v3.7.3
COPY observability/prometheus.yaml /etc/prometheus/autodev.yml