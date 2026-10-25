using './family-demo.bicep'

param location = 'eastus2'
param namePrefix = 'autodev-family'
param customDomain = 'autodev.example.com'
param cloudflareTunnelToken = readEnvironmentVariable('AUTODEV_CLOUDFLARE_TUNNEL_TOKEN')

param registryName = 'replace-me'
param registryResourceGroupName = 'autodev'
param apiImage = 'replace-me.azurecr.io/autodev-api@sha256:replace-me'
param webImage = 'replace-me.azurecr.io/autodev-web@sha256:replace-me'

param sessionPoolName = 'autodev-family-sessions'
param sessionPoolResourceGroupName = 'autodev'
param sessionPoolEndpoint = 'https://replace-me.dynamicsessions.io'
param sessionExecutorRoleDefinitionId = '00000000-0000-0000-0000-000000000000'
param sessionPoolNetworkMode = 'none'

param foundryResponsesEndpoint = 'https://replace-me.services.ai.azure.com/api/projects/replace-me/openai/v1/responses'
param foundryDefaultModel = 'replace-me-primary-deployment'
param foundryModels = [
  'replace-me-fast-deployment'
]
param foundryAccountName = 'replace-me'
param foundryAccountResourceGroupName = 'autodev'
param foundryRoleDefinitionId = '00000000-0000-0000-0000-000000000000'

param tenantId = '00000000-0000-0000-0000-000000000000'
param oidcClientId = '00000000-0000-0000-0000-000000000000'
param oidcAudience = '00000000-0000-0000-0000-000000000000'
param oidcClientSecret = readEnvironmentVariable('AUTODEV_OIDC_CLIENT_SECRET')

param postgresPassword = readEnvironmentVariable('AUTODEV_POSTGRES_PASSWORD')
param credentialMasterKey = readEnvironmentVariable('AUTODEV_CREDENTIAL_MASTER_KEY')
param adminUsername = 'azureuser'
param adminSshPublicKey = readEnvironmentVariable('AUTODEV_ADMIN_SSH_PUBLIC_KEY')
param vmSize = 'Standard_B2as_v2'
param osDiskSizeGb = 128

// Cheapest option. Change to 'natGateway' if explicit default outbound access is unavailable.
param outboundConnectivity = 'defaultOutbound'
