# Azure session deployment

The Azure sandbox uses a custom Azure Container Apps dynamic session pool. Each session runs in a Hyper-V boundary. Deploy separate pools for the `none` and `bridge` agent network profiles; a pool's egress mode is immutable for an active workload and the API fails closed on a profile mismatch.

The production control plane runs the API and worker as separate Container Apps. PostgreSQL owns durable application and execution state, Redis carries replayable events, Blob Storage owns workspace revisions and evidence, and Key Vault stores tenant connector credentials. API replicas do not execute queued tasks.

## Build the image

```bash
az acr build \
  --registry <registry-name> \
  --image autodev-session:1.0.0 \
  --file docker/azure-session/Dockerfile .
```

Pin `sessionImage` to an immutable digest for production. Grant the user-assigned identity passed as `registryIdentityResourceId` the `AcrPull` role on the registry.

## Deploy the pool

Create an Azure Container Apps managed environment, update `infra/azure/main.bicepparam`, then run:

```bash
az deployment group create \
  --resource-group <resource-group> \
  --template-file infra/azure/main.bicep \
  --parameters infra/azure/main.bicepparam
```

Grant the API workload identity the Azure ContainerApps Session Executor role scoped to the emitted `sessionPoolId`. Configure the API with:

```text
WORKBENCH_SANDBOX_PROVIDER=azure
WORKBENCH_AZURE_SESSION_POOL_ENDPOINT=<sessionPoolEndpoint>
WORKBENCH_AZURE_SESSION_POOL_NETWORK_MODE=none
WORKBENCH_AZURE_SESSION_POOL_PROFILE=python-hyperv-2cpu-2gi-no-egress
WORKBENCH_AZURE_SESSION_POOL_CPU_LIMIT=2
WORKBENCH_AZURE_SESSION_POOL_MEMORY_MB=2048
```

The API authenticates with `DefaultAzureCredential`. Do not put Azure credentials in agent definitions or session environment variables.

## Deploy the control plane

Build and push the API image, then pin it by digest:

```bash
az acr build \
  --registry <registry-name> \
  --image autodev-api:<version> \
  --file apps/api/Dockerfile .
```

Create an ACR pull identity and grant it `AcrPull`. Set the session executor role definition GUID from your tenant's Azure ContainerApps Session Executor role:

```bash
az role definition list \
  --name "Azure ContainerApps Session Executor" \
  --query '[0].name' -o tsv
```

Update `infra/azure/control-plane.bicepparam`. Supply secrets through environment variables so they do not enter parameter files or deployment history:

```bash
export AUTODEV_POSTGRES_ADMIN_PASSWORD='<generated-password>'
export AUTODEV_GITHUB_OAUTH_CLIENT_ID='<client-id>'
export AUTODEV_GITHUB_OAUTH_CLIENT_SECRET='<client-secret>'

az deployment group create \
  --resource-group <resource-group> \
  --template-file infra/azure/control-plane.bicep \
  --parameters infra/azure/control-plane.bicepparam
```

The control-plane template provisions:

- A zone-redundant Container Apps environment with an externally routed API and independently scaled worker.
- PostgreSQL Flexible Server with TLS, backups, and zone-redundant high availability.
- TLS-only Azure Cache for Redis for event streams.
- ZRS Blob Storage with soft deletion for workspace revisions and evidence.
- RBAC-enabled Key Vault with purge protection for tenant connector credentials.
- A user-assigned workload identity with Blob Data Contributor, Key Vault Secrets Officer, and session executor access.
- PostgreSQL-based KEDA scaling for queued execution jobs.

The API image embeds agent, policy, skill, harness, MCP, workflow, evaluation, and prompt definitions. Publish a new immutable image when these definitions change; do not mount mutable registry folders in Azure.

The template currently enables Azure-service public endpoints for PostgreSQL, Redis, Storage, and Key Vault to keep the first deployment self-contained. Before handling production tenant data, attach the Container Apps environment to a VNet, add private endpoints and private DNS for each state service, and disable their public network access.

The worker uses the Azure session provider and must not receive a Docker socket. `AZURE_CLIENT_ID` selects the workload identity explicitly because each Container App also has an ACR pull identity.

Grant the emitted workload identity the model invocation role required by the configured Microsoft Foundry project. The Foundry project may live in another resource group or subscription, so this assignment is intentionally outside the control-plane template.

## Operations

The deployment enables startup and liveness probes, sends all pool logs and metrics to Log Analytics, and alerts when a pool configured with ready capacity reports no ready sessions for five minutes.

Useful Log Analytics tables:

```kusto
AppEnvSessionConsoleLogs
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
```

```kusto
AppEnvSessionLifecycleLogs
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
```

```kusto
AppEnvSessionPoolEvents
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
```

The custom image rejects unsafe archives and credential-like environment names. The control plane imports the latest host workspace before every command, exports remote changes immediately afterward, and refuses to apply an export if the host changed concurrently.
