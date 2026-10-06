# Azure session deployment

The Azure sandbox uses a custom Azure Container Apps dynamic session pool. Each session runs in a Hyper-V boundary. Deploy separate pools for the `none` and `bridge` agent network profiles; a pool's egress mode is immutable for an active workload and the API fails closed on a profile mismatch.

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
