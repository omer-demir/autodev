# Private Azure family demo through Cloudflare

This deployment keeps the AutoDev origin on one cost-conscious Azure VM and makes Cloudflare Tunnel the only application ingress. It is intended for a small, mutually trusted family group, not hostile public multi-tenancy.

## Architecture and boundaries

- The VM has no public IP and its subnet NSG denies all inbound traffic.
- `cloudflared` initiates an outbound tunnel and sends requests to a private Caddy gateway in the Docker network.
- Caddy sends `/api/*` and `/health` to FastAPI and all other paths to Next.js. WebSockets are proxied automatically.
- PostgreSQL and Redis run on the VM and publish no host ports.
- Blob Storage, Key Vault, and optionally Microsoft Foundry use private endpoints and private DNS.
- The VM system-assigned managed identity pulls images, invokes Foundry, accesses Blob/Key Vault, and executes dynamic sessions. No Azure user credential is stored on the VM.
- Dynamic Azure Container Apps sessions provide the untrusted execution boundary. The API and worker do not receive the Docker socket.
- Cloudflare Access should allow only exact family email addresses. AutoDev still performs its own tenant-specific Entra OIDC login and RBAC.

The low-cost `defaultOutbound` mode gives the private VM explicit Azure default outbound connectivity without a VM public IP. If it is unavailable in the selected subscription or region, choose `natGateway`; that is operationally stronger but adds a fixed monthly NAT Gateway and public-IP charge. Neither mode permits inbound connections to the VM.

Basic ACR remains on an RBAC-protected public service endpoint because ACR Private Link requires the substantially more expensive Premium tier. It is used only for authenticated outbound image pulls and is not an application ingress. The dynamic-session management endpoint is also outbound-only and requires Azure RBAC.

## Files

- `infra/azure/family-demo-foundation.bicep`: Basic ACR, session pull identity, Log Analytics, and a Container Apps managed environment.
- `infra/azure/main.bicep`: Existing custom dynamic session pool.
- `infra/azure/family-demo.bicep`: Private VM, VNet, storage, Key Vault, private endpoints, identity roles, secrets, and bootstrap.
- `infra/azure/family-demo/bootstrap.sh`: Installs the runtime, writes the reduced Compose stack, and configures nightly PostgreSQL backups.

## Prerequisites

Register the Azure resource providers used by the templates and install current Azure CLI/Bicep support. Create a resource group in a region that supports custom Container Apps dynamic sessions and the selected VM size.

```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.Compute
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.Network
az provider register --namespace Microsoft.Storage
az group create --name autodev-family --location eastus2
```

The deploying principal needs permission to create infrastructure and role assignments.

## 1. Deploy the build and session foundation

```bash
az deployment group create \
  --resource-group autodev-family \
  --name autodev-family-foundation \
  --template-file infra/azure/family-demo-foundation.bicep \
  --parameters infra/azure/family-demo-foundation.bicepparam
```

Capture its outputs:

```bash
REGISTRY=$(az deployment group show -g autodev-family -n autodev-family-foundation --query properties.outputs.registryName.value -o tsv)
REGISTRY_SERVER=$(az deployment group show -g autodev-family -n autodev-family-foundation --query properties.outputs.registryServer.value -o tsv)
REGISTRY_ID=$(az deployment group show -g autodev-family -n autodev-family-foundation --query properties.outputs.registryResourceId.value -o tsv)
PULL_IDENTITY_ID=$(az deployment group show -g autodev-family -n autodev-family-foundation --query properties.outputs.sessionPullIdentityResourceId.value -o tsv)
SESSION_ENVIRONMENT_ID=$(az deployment group show -g autodev-family -n autodev-family-foundation --query properties.outputs.containerAppsEnvironmentId.value -o tsv)
```

## 2. Build immutable application and session images

The web image must use same-origin browser requests and its server-side rewrite must target the Compose API service.

```bash
az acr build --registry "$REGISTRY" --image autodev-api:family \
  --file apps/api/Dockerfile .

az acr build --registry "$REGISTRY" --image autodev-web:family \
  --file apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL= \
  --build-arg WORKBENCH_API_URL=http://api:8000 .

az acr build --registry "$REGISTRY" --image autodev-session:family \
  --file docker/azure-session/Dockerfile .
```

Resolve each tag to a digest and put the resulting `repository@sha256:...` references in the parameter file. Do not deploy mutable tags for the API or web images.

```bash
API_DIGEST=$(az acr manifest show-metadata -r "$REGISTRY" -n autodev-api:family --query digest -o tsv)
WEB_DIGEST=$(az acr manifest show-metadata -r "$REGISTRY" -n autodev-web:family --query digest -o tsv)
SESSION_DIGEST=$(az acr manifest show-metadata -r "$REGISTRY" -n autodev-session:family --query digest -o tsv)
```

## 3. Deploy the zero-ready-capacity session pool

For the initial family deployment, use no network egress, no pre-warmed sessions, and at most two concurrent sessions. Create a separate `EgressEnabled` pool later if a narrowly governed workflow genuinely needs sandbox network access.

```bash
az deployment group create \
  --resource-group autodev-family \
  --name autodev-family-sessions \
  --template-file infra/azure/main.bicep \
  --parameters \
    sessionPoolName=autodev-family-sessions \
    containerAppsEnvironmentId="$SESSION_ENVIRONMENT_ID" \
    sessionImage="$REGISTRY_SERVER/autodev-session@$SESSION_DIGEST" \
    registryServer="$REGISTRY_SERVER" \
    registryIdentityResourceId="$PULL_IDENTITY_ID" \
    networkStatus=EgressDisabled \
    readySessionInstances=0 \
    maxConcurrentSessions=2 \
    cooldownPeriodInSeconds=180
```

Capture the endpoint and role definition:

```bash
SESSION_ENDPOINT=$(az deployment group show -g autodev-family -n autodev-family-sessions --query properties.outputs.sessionPoolEndpoint.value -o tsv)
SESSION_EXECUTOR_ROLE=$(az role definition list --name "Azure ContainerApps Session Executor" --query '[0].name' -o tsv)
```

## 4. Configure Microsoft Foundry

Deploy one inexpensive model for normal use and optionally a stronger model for difficult tasks. Both deployment names can be listed in `foundryModels`; the UI will expose them while `foundryDefaultModel` remains the default.

The VM uses `DefaultAzureCredential` and its system-assigned identity. Set `foundryAccountName` and the model-invocation role definition GUID so the template grants that identity access at the Foundry account. The exact least-privilege role depends on the Foundry resource type and tenant policy; obtain the approved role GUID rather than using an Owner or Contributor role.

When `foundryAccountName` is set, the template creates a Foundry private endpoint and links the `services.ai.azure.com`, Cognitive Services, and Azure OpenAI private DNS zones. Verify model calls from the VM before disabling public network access on the existing Foundry account. The template deliberately does not mutate the networking policy of an existing account.

The main agent runtime supports Foundry directly. The separate behavioral evaluation adapters currently support Copilot or Ollama, so this family profile leaves evaluator selection on Ollama; ordinary agent tasks do not require Copilot CLI.

## 5. Configure Entra and Cloudflare

Create a single-tenant Entra web application with this redirect URI:

```text
https://autodev.example.com/api/auth/callback
```

Define app roles named `admin`, `developer`, `reviewer`, and `viewer`. Assign yourself `admin`; initially assign family members `viewer`, then promote only those who need task execution to `developer`. Require user assignment on the enterprise application.

Create a remotely managed Cloudflare Tunnel and copy its token. In the tunnel dashboard, configure the public hostname with this origin service:

```text
http://gateway:8080
```

Protect the entire hostname with Cloudflare Access. Use exact family email addresses, require MFA where possible, and do not add a broad domain or `Everyone` rule. No DNS record should point directly to Azure.

## 6. Supply secrets and deploy the private VM

Edit `infra/azure/family-demo.bicepparam` with the foundation outputs, digest-pinned image references, session endpoint, Foundry values, tenant/client IDs, and custom domain. Supply secrets only through environment variables:

```bash
export AUTODEV_CLOUDFLARE_TUNNEL_TOKEN='<tunnel-token>'
export AUTODEV_OIDC_CLIENT_SECRET='<entra-client-secret>'
export AUTODEV_POSTGRES_PASSWORD='<url-safe-random-value>'
export AUTODEV_CREDENTIAL_MASTER_KEY='<stable-high-entropy-value>'
export AUTODEV_ADMIN_SSH_PUBLIC_KEY="$(cat ~/.ssh/id_ed25519.pub)"
```

Keep the credential master key stable and backed up even though the deployment uses Key Vault for connector credentials. Validate with What-If, then deploy:

```bash
az deployment group what-if \
  --resource-group autodev-family \
  --template-file infra/azure/family-demo.bicep \
  --parameters infra/azure/family-demo.bicepparam

az deployment group create \
  --resource-group autodev-family \
  --name autodev-family-runtime \
  --template-file infra/azure/family-demo.bicep \
  --parameters infra/azure/family-demo.bicepparam
```

The secure parameters are written to Key Vault. Bootstrap retrieves them through the private endpoint after managed-identity role propagation. The first startup can therefore take several minutes.

## 7. Verify without opening SSH

Use Azure Run Command to inspect the private VM:

```bash
az vm run-command invoke \
  --resource-group autodev-family \
  --name autodev-family-vm \
  --command-id RunShellScript \
  --scripts 'cloud-init status --wait; cd /opt/autodev && docker compose ps'
```

Check that:

1. The VM NIC has no public IP.
2. The NSG has no inbound allow rule.
3. PostgreSQL, Redis, API, and web have no published host ports.
4. Storage and Key Vault reject public network access.
5. The custom domain is blocked by Cloudflare Access for non-family identities.
6. AutoDev redirects accepted users through the tenant-specific Entra application.
7. A simple task invokes Foundry under the VM managed identity.
8. Task execution creates an Azure dynamic session and does not access the VM Docker daemon.

Bootstrap logs are in `/var/log/autodev-bootstrap.log`. Application status and logs are available with `docker compose ps` and `docker compose logs` under `/opt/autodev` through Run Command.

## Operations and cost controls

- Keep `readySessionInstances=0` and a low session concurrency limit.
- Keep one worker container; it serializes queue processing on this VM.
- Use Azure budgets and Foundry quotas. Budget notifications are not a hard spending cutoff.
- Prefer a small default model and select the stronger deployment only when needed.
- Nightly compressed PostgreSQL dumps are uploaded to the private `autodev-backups` container by a systemd timer.
- Blob soft deletion is 14 days. Add a lifecycle policy when workspace volume grows.
- The local PostgreSQL and Redis data live on the OS disk. A VM deletion can destroy them; verify Blob backups before destructive maintenance.
- Stop/deallocate the VM when the family does not need the service. Cloudflare will show the origin as unavailable until it is restarted.
- Pin the PostgreSQL, Redis, Caddy, and cloudflared images by digest after the first successful test.
- Rotate the Cloudflare Tunnel token and Entra client secret through Key Vault, then rerun bootstrap or update `/opt/autodev/.env` through Run Command and restart `autodev.service`.

This profile minimizes fixed managed-service costs while preserving private application ingress and isolating untrusted execution in Azure dynamic sessions.
