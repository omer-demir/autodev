FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git python3 python3-pip python3-pytest \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 sandbox

COPY docker/azure-session/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
COPY docker/azure-session/app.py /opt/autodev-session/app.py

ENV AUTODEV_WORKSPACE=/workspace/project
WORKDIR /workspace/project
EXPOSE 8080
CMD ["uvicorn", "app:app", "--app-dir", "/opt/autodev-session", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]