#!/usr/bin/env bash
set -Eeuo pipefail

exec > >(tee -a /var/log/autodev-bootstrap.log) 2>&1
export DEBIAN_FRONTEND=noninteractive

retry() {
  local attempts="$1"
  shift
  local delay="$1"
  shift
  local count=1
  until "$@"; do
    if (( count >= attempts )); then
      echo "Command failed after ${count} attempts: $*" >&2
      return 1
    fi
    echo "Attempt ${count} failed; retrying in ${delay}s: $*" >&2
    count=$((count + 1))
    sleep "${delay}"
  done
}

apt-get update
apt-get install --yes --no-install-recommends \
  ca-certificates curl docker.io docker-compose-v2 gzip jq python3
systemctl enable --now docker

if ! command -v az >/dev/null 2>&1; then
  curl --fail --silent --show-error --location https://aka.ms/InstallAzureCLIDeb | bash
fi

install -d -m 0750 /opt/autodev
install -d -m 0750 /opt/autodev/data/postgres
install -d -m 0750 /opt/autodev/data/redis
install -d -m 0750 /opt/autodev/data/workspaces

retry 30 10 az login --identity --allow-no-subscriptions --output none
retry 30 10 az acr login --name '__REGISTRY_NAME__' --output none

get_secret() {
  retry 60 10 az keyvault secret show \
    --vault-name '__KEY_VAULT_NAME__' \
    --name "$1" \
    --query value \
    --output tsv
}

validate_env_secret() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" || "${value}" == *$'\n'* || "${value}" == *"'"* ]]; then
    echo "${name} must be non-empty and contain neither a newline nor a single quote" >&2
    exit 1
  fi
}

cloudflare_tunnel_token="$(get_secret cloudflare-tunnel-token)"
postgres_password="$(get_secret postgres-password)"
credential_master_key="$(get_secret credential-master-key)"
oidc_client_secret="$(get_secret oidc-client-secret)"
validate_env_secret CLOUDFLARE_TUNNEL_TOKEN "${cloudflare_tunnel_token}"
validate_env_secret POSTGRES_PASSWORD "${postgres_password}"
validate_env_secret WORKBENCH_CREDENTIAL_MASTER_KEY "${credential_master_key}"
validate_env_secret WORKBENCH_OIDC_CLIENT_SECRET "${oidc_client_secret}"

postgres_password_encoded="$(POSTGRES_PASSWORD="${postgres_password}" python3 - <<'PY'
import os
from urllib.parse import quote
print(quote(os.environ["POSTGRES_PASSWORD"], safe=""))
PY
)"

cat >/opt/autodev/.env <<EOF
POSTGRES_PASSWORD='${postgres_password}'
CLOUDFLARE_TUNNEL_TOKEN='${cloudflare_tunnel_token}'
WORKBENCH_DATABASE_URL='postgresql+psycopg://autodev:${postgres_password_encoded}@postgres:5432/autodev'
WORKBENCH_EXECUTION_DISPATCH='durable'
WORKBENCH_REDIS_URL='redis://redis:6379/0'
WORKBENCH_EVIDENCE_PROVIDER='azure_blob'
WORKBENCH_EVIDENCE_CONTAINER='autodev-evidence'
WORKBENCH_WORKSPACE_DIR='/workspaces'
WORKBENCH_WORKSPACE_SNAPSHOT_PROVIDER='azure_blob'
WORKBENCH_WORKSPACE_SNAPSHOT_REQUIRED='true'
WORKBENCH_WORKSPACE_SNAPSHOT_CONTAINER='autodev-workspaces'
WORKBENCH_AZURE_STORAGE_ACCOUNT_URL='https://__STORAGE_ACCOUNT_NAME__.blob.core.windows.net'
WORKBENCH_EXECUTION_MODE='real'
WORKBENCH_GOVERNANCE_PROVIDER='agent_os'
WORKBENCH_RUNTIME_SUPERVISOR_PROVIDER='microsoft_agent_hypervisor'
WORKBENCH_MODEL_PROVIDER='foundry'
WORKBENCH_MODEL_NAME='__FOUNDRY_DEFAULT_MODEL__'
WORKBENCH_MODEL_FALLBACK_PROVIDER='foundry'
WORKBENCH_MODEL_FALLBACK_NAME='__FOUNDRY_DEFAULT_MODEL__'
WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT='__FOUNDRY_ENDPOINT__'
WORKBENCH_FOUNDRY_MODEL='__FOUNDRY_DEFAULT_MODEL__'
WORKBENCH_FOUNDRY_MODELS='__FOUNDRY_MODELS__'
WORKBENCH_EVALUATOR_PROVIDER='ollama'
WORKBENCH_EVALUATOR_MODEL='gemma4:e2b'
WORKBENCH_MODEL_REQUEST_TIMEOUT_SECONDS='300'
WORKBENCH_AGENT_TURN_TIMEOUT_SECONDS='1800'
WORKBENCH_SANDBOX_COMMAND_TIMEOUT_SECONDS='1800'
WORKBENCH_MAX_AGENT_STEPS='30'
WORKBENCH_SANDBOX_PROVIDER='azure'
WORKBENCH_AZURE_SESSION_POOL_ENDPOINT='__SESSION_POOL_ENDPOINT__'
WORKBENCH_AZURE_SESSION_POOL_NETWORK_MODE='__SESSION_POOL_NETWORK_MODE__'
WORKBENCH_AZURE_SESSION_POOL_PROFILE='python-hyperv-2cpu-2gi-family'
WORKBENCH_AZURE_SESSION_POOL_CPU_LIMIT='2'
WORKBENCH_AZURE_SESSION_POOL_MEMORY_MB='2048'
WORKBENCH_CREDENTIAL_PROVIDER='azure_key_vault'
WORKBENCH_AZURE_KEY_VAULT_URL='https://__KEY_VAULT_NAME__.vault.azure.net'
WORKBENCH_CREDENTIAL_MASTER_KEY='${credential_master_key}'
WORKBENCH_AUTH_MODE='oidc'
WORKBENCH_OIDC_ISSUER='__OIDC_ISSUER__'
WORKBENCH_OIDC_AUDIENCE='__OIDC_AUDIENCE__'
WORKBENCH_OIDC_JWKS_URL='__OIDC_JWKS_URL__'
WORKBENCH_OIDC_AUTHORIZATION_URL='__OIDC_AUTHORIZATION_URL__'
WORKBENCH_OIDC_TOKEN_URL='__OIDC_TOKEN_URL__'
WORKBENCH_OIDC_CLIENT_ID='__OIDC_CLIENT_ID__'
WORKBENCH_OIDC_CLIENT_SECRET='${oidc_client_secret}'
WORKBENCH_OIDC_REDIRECT_URI='__WEB_APP_URL__/api/auth/callback'
WORKBENCH_OIDC_SCOPES='openid profile email'
WORKBENCH_OIDC_ORGANIZATION_CLAIM='tid'
WORKBENCH_OIDC_ROLES_CLAIM='roles'
WORKBENCH_OIDC_AUTO_PROVISION='true'
WORKBENCH_SESSION_TTL_HOURS='8'
WORKBENCH_SESSION_COOKIE_SECURE='true'
WORKBENCH_API_URL='__WEB_APP_URL__'
WORKBENCH_WEB_APP_URL='__WEB_APP_URL__'
WORKBENCH_MCP_ALLOWED_HOSTS='__CUSTOM_DOMAIN__'
WORKBENCH_MCP_ALLOWED_ORIGINS='__WEB_APP_URL__'
EOF
chmod 0600 /opt/autodev/.env

cat >/opt/autodev/Caddyfile <<'EOF'
:8080 {
  encode zstd gzip

  @api path /api/* /health
  reverse_proxy @api api:8000
  reverse_proxy web:3000

  header {
    -Server
    X-Content-Type-Options nosniff
    Referrer-Policy strict-origin-when-cross-origin
  }
}
EOF

cat >/opt/autodev/compose.yaml <<'EOF'
name: autodev-family

services:
  postgres:
    image: __POSTGRES_IMAGE__
    restart: unless-stopped
    environment:
      POSTGRES_DB: autodev
      POSTGRES_USER: autodev
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U autodev -d autodev"]
      interval: 5s
      timeout: 5s
      retries: 30
    volumes:
      - /opt/autodev/data/postgres:/var/lib/postgresql/data
    networks: [control]

  redis:
    image: __REDIS_IMAGE__
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 30
    volumes:
      - /opt/autodev/data/redis:/data
    networks: [control]

  api:
    image: __API_IMAGE__
    restart: unless-stopped
    env_file: .env
    environment:
      WORKBENCH_OTEL_SERVICE_NAME: autodev-api
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 30
    volumes:
      - /opt/autodev/data/workspaces:/workspaces
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    networks: [control]

  worker:
    image: __API_IMAGE__
    restart: unless-stopped
    command: ["python", "-m", "app.worker"]
    env_file: .env
    environment:
      WORKBENCH_OTEL_SERVICE_NAME: autodev-worker
    volumes:
      - /opt/autodev/data/workspaces:/workspaces
    depends_on:
      api: {condition: service_healthy}
    networks: [control]

  web:
    image: __WEB_IMAGE__
    restart: unless-stopped
    environment:
      WORKBENCH_API_URL: http://api:8000
      NEXT_TELEMETRY_DISABLED: "1"
    depends_on:
      api: {condition: service_healthy}
    networks: [control]

  gateway:
    image: __GATEWAY_IMAGE__
    restart: unless-stopped
    command: ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
    volumes:
      - /opt/autodev/Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      api: {condition: service_healthy}
      web: {condition: service_started}
    networks: [control]

  cloudflared:
    image: __CLOUDFLARED_IMAGE__
    restart: unless-stopped
    command: ["tunnel", "--no-autoupdate", "run", "--token", "${CLOUDFLARE_TUNNEL_TOKEN}"]
    depends_on:
      gateway: {condition: service_started}
    networks: [control]

networks:
  control:
    internal: false
EOF

cat >/opt/autodev/start.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
cd /opt/autodev
az login --identity --allow-no-subscriptions --output none
az acr login --name '__REGISTRY_NAME__' --output none
for attempt in $(seq 1 30); do
  if docker compose pull; then
    docker compose up --detach --remove-orphans
    exit 0
  fi
  echo "Image pull attempt ${attempt} failed; retrying in 10 seconds" >&2
  sleep 10
done
exit 1
EOF
chmod 0750 /opt/autodev/start.sh

cat >/etc/systemd/system/autodev.service <<'EOF'
[Unit]
Description=AutoDev family deployment
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/autodev
ExecStart=/opt/autodev/start.sh
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes
TimeoutStartSec=900

[Install]
WantedBy=multi-user.target
EOF

cat >/opt/autodev/backup.sh <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
cd /opt/autodev
backup="/tmp/autodev-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
docker compose exec -T postgres pg_dump --clean --if-exists --no-owner -U autodev autodev | gzip -9 >"${backup}"
az login --identity --allow-no-subscriptions --output none
az storage blob upload \
  --auth-mode login \
  --account-name '__STORAGE_ACCOUNT_NAME__' \
  --container-name autodev-backups \
  --name "postgres/$(basename "${backup}")" \
  --file "${backup}" \
  --overwrite false \
  --output none
rm -f "${backup}"
EOF
chmod 0750 /opt/autodev/backup.sh

cat >/etc/systemd/system/autodev-backup.service <<'EOF'
[Unit]
Description=Back up the AutoDev PostgreSQL database
After=autodev.service

[Service]
Type=oneshot
ExecStart=/opt/autodev/backup.sh
EOF

cat >/etc/systemd/system/autodev-backup.timer <<'EOF'
[Unit]
Description=Nightly AutoDev database backup

[Timer]
OnCalendar=*-*-* 03:15:00 UTC
Persistent=true
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable autodev.service autodev-backup.timer
retry 30 10 systemctl start autodev.service
systemctl start autodev-backup.timer

echo "AutoDev bootstrap completed. Cloudflare must route the public hostname to http://gateway:8080."
