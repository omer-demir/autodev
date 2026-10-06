FROM grafana/grafana:12.3.0
COPY observability/grafana/provisioning /etc/grafana/provisioning
COPY observability/grafana/dashboards /etc/grafana/dashboards