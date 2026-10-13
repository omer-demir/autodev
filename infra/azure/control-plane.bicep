@description('Azure region for the AutoDev control plane.')
param location string = resourceGroup().location

@minLength(3)
@maxLength(18)
@description('Lowercase prefix used for globally unique resource names.')
param namePrefix string

@description('API container image pinned by digest in production.')
param apiImage string

@description('Worker container image pinned by digest in production.')
param workerImage string = apiImage

@description('Azure Container Registry host, for example contoso.azurecr.io.')
param registryServer string

@description('User-assigned identity resource ID with AcrPull on the registry.')
param registryIdentityResourceId string

@description('Name of an existing dynamic session pool in this resource group.')
param sessionPoolName string

@description('Management endpoint emitted by the dynamic session pool deployment.')
param sessionPoolEndpoint string

@description('Built-in Azure ContainerApps Session Executor role definition GUID.')
param sessionExecutorRoleDefinitionId string

@allowed([
  'none'
  'bridge'
])
param sessionPoolNetworkMode string = 'bridge'

param sessionPoolProfile string = 'python-hyperv-2cpu-2gi-egress'

@secure()
@minLength(16)
param postgresAdminPassword string

param postgresAdminLogin string = 'autodevadmin'

@description('Microsoft Foundry Responses endpoint used by workers.')
param foundryResponsesEndpoint string

param foundryModel string = 'gpt-5.4-mini'

@allowed([
  'local'
  'oidc'
])
param authMode string = 'oidc'

param oidcIssuer string = ''
param oidcAudience string = ''
param oidcJwksUrl string = ''

@secure()
param githubOAuthClientId string = ''

@secure()
param githubOAuthClientSecret string = ''

param webAppUrl string

@minValue(1)
param apiMinReplicas int = 2

@minValue(1)
param apiMaxReplicas int = 10

@minValue(1)
param workerMinReplicas int = 1

@minValue(1)
param workerMaxReplicas int = 20

@minValue(30)
param logRetentionDays int = 30

param tags object = {}

var token = uniqueString(subscription().id, resourceGroup().id, namePrefix)
var storageName = take(toLower(replace('${namePrefix}${token}', '-', '')), 24)
var keyVaultName = take(toLower('${namePrefix}-${token}-kv'), 24)
var postgresName = take(toLower('${namePrefix}-${token}-pg'), 63)
var redisName = take(toLower('${namePrefix}-${token}-redis'), 63)
var environmentName = take(toLower('${namePrefix}-environment'), 32)
var identityName = take(toLower('${namePrefix}-workload'), 128)
var apiName = take(toLower('${namePrefix}-api'), 32)
var workerName = take(toLower('${namePrefix}-worker'), 32)
var apiHost = '${apiName}.${environment.properties.defaultDomain}'
var databaseUrl = 'postgresql+psycopg://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/autodev?sslmode=require'
var postgresScaleConnection = 'postgresql://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/autodev?sslmode=require'
var redisUrl = 'rediss://:${uriComponent(redis.listKeys().primaryKey)}@${redis.properties.hostName}:${redis.properties.sslPort}/0'
var commonSecrets = [
  {
    name: 'database-url'
    value: databaseUrl
  }
  {
    name: 'postgres-scale-connection'
    value: postgresScaleConnection
  }
  {
    name: 'redis-url'
    value: redisUrl
  }
  {
    name: 'github-oauth-client-id'
    value: githubOAuthClientId
  }
  {
    name: 'github-oauth-client-secret'
    value: githubOAuthClientSecret
  }
]
var commonEnvironment = [
  {
    name: 'AZURE_CLIENT_ID'
    value: workloadIdentity.properties.clientId
  }
  {
    name: 'WORKBENCH_DATABASE_URL'
    secretRef: 'database-url'
  }
  {
    name: 'WORKBENCH_EXECUTION_DISPATCH'
    value: 'durable'
  }
  {
    name: 'WORKBENCH_REDIS_URL'
    secretRef: 'redis-url'
  }
  {
    name: 'WORKBENCH_WORKSPACE_DIR'
    value: '/tmp/workspaces'
  }
  {
    name: 'WORKBENCH_WORKSPACE_SNAPSHOT_PROVIDER'
    value: 'azure_blob'
  }
  {
    name: 'WORKBENCH_WORKSPACE_SNAPSHOT_REQUIRED'
    value: 'true'
  }
  {
    name: 'WORKBENCH_AZURE_STORAGE_ACCOUNT_URL'
    value: storage.properties.primaryEndpoints.blob
  }
  {
    name: 'WORKBENCH_EVIDENCE_PROVIDER'
    value: 'azure_blob'
  }
  {
    name: 'WORKBENCH_EVIDENCE_DIR'
    value: '/tmp/evidence'
  }
  {
    name: 'WORKBENCH_SANDBOX_PROVIDER'
    value: 'azure'
  }
  {
    name: 'WORKBENCH_AZURE_SESSION_POOL_ENDPOINT'
    value: sessionPoolEndpoint
  }
  {
    name: 'WORKBENCH_AZURE_SESSION_POOL_NETWORK_MODE'
    value: sessionPoolNetworkMode
  }
  {
    name: 'WORKBENCH_AZURE_SESSION_POOL_PROFILE'
    value: sessionPoolProfile
  }
  {
    name: 'WORKBENCH_CREDENTIAL_PROVIDER'
    value: 'azure_key_vault'
  }
  {
    name: 'WORKBENCH_AZURE_KEY_VAULT_URL'
    value: keyVault.properties.vaultUri
  }
  {
    name: 'WORKBENCH_MODEL_PROVIDER'
    value: 'foundry'
  }
  {
    name: 'WORKBENCH_FOUNDRY_RESPONSES_ENDPOINT'
    value: foundryResponsesEndpoint
  }
  {
    name: 'WORKBENCH_FOUNDRY_MODEL'
    value: foundryModel
  }
  {
    name: 'WORKBENCH_AUTH_MODE'
    value: authMode
  }
  {
    name: 'WORKBENCH_OIDC_ISSUER'
    value: oidcIssuer
  }
  {
    name: 'WORKBENCH_OIDC_AUDIENCE'
    value: oidcAudience
  }
  {
    name: 'WORKBENCH_OIDC_JWKS_URL'
    value: oidcJwksUrl
  }
  {
    name: 'WORKBENCH_GITHUB_OAUTH_CLIENT_ID'
    secretRef: 'github-oauth-client-id'
  }
  {
    name: 'WORKBENCH_GITHUB_OAUTH_CLIENT_SECRET'
    secretRef: 'github-oauth-client-secret'
  }
  {
    name: 'WORKBENCH_WEB_APP_URL'
    value: webAppUrl
  }
  {
    name: 'WORKBENCH_MCP_ALLOWED_HOSTS'
    value: apiHost
  }
  {
    name: 'WORKBENCH_MCP_ALLOWED_ORIGINS'
    value: webAppUrl
  }
]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  tags: tags
  properties: {
    retentionInDays: logRetentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    zoneRedundant: true
  }
}

resource workloadIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: {
    name: 'Standard_ZRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 14
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 14
    }
  }
}

resource workspaceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'autodev-workspaces'
  properties: {
    publicAccess: 'None'
  }
}

resource evidenceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'autodev-evidence'
  properties: {
    publicAccess: 'None'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    softDeleteRetentionInDays: 90
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: postgresName
  location: location
  tags: tags
  sku: {
    name: 'Standard_D2ds_v5'
    tier: 'GeneralPurpose'
  }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    backup: {
      backupRetentionDays: 14
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'ZoneRedundant'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    storage: {
      autoGrow: 'Enabled'
      storageSizeGB: 128
    }
    version: '16'
  }
}

resource postgresAzureAccess 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: 'autodev'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource redis 'Microsoft.Cache/redis@2024-03-01' = {
  name: redisName
  location: location
  tags: tags
  properties: {
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    redisVersion: '6'
    sku: {
      capacity: 1
      family: 'C'
      name: 'Standard'
    }
  }
}

resource storageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, workloadIdentity.properties.principalId, 'blob-data-contributor')
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: workloadIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, workloadIdentity.properties.principalId, 'secrets-officer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
    principalId: workloadIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource sessionPool 'Microsoft.App/sessionPools@2025-07-01' existing = {
  name: sessionPoolName
}

resource sessionExecutorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sessionPool.id, workloadIdentity.properties.principalId, sessionExecutorRoleDefinitionId)
  scope: sessionPool
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sessionExecutorRoleDefinitionId)
    principalId: workloadIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workloadIdentity.id}': {}
      '${registryIdentityResourceId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          identity: registryIdentityResourceId
          server: registryServer
        }
      ]
      secrets: commonSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: concat(commonEnvironment, [
            {
              name: 'WORKBENCH_OTEL_SERVICE_NAME'
              value: 'autodev-api'
            }
          ])
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 15
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: apiMinReplicas
        maxReplicas: apiMaxReplicas
        rules: [
          {
            name: 'http'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    database
    evidenceContainer
    keyVaultRole
    postgresAzureAccess
    sessionExecutorRole
    storageRole
    workspaceContainer
  ]
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: workerName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workloadIdentity.id}': {}
      '${registryIdentityResourceId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          identity: registryIdentityResourceId
          server: registryServer
        }
      ]
      secrets: commonSecrets
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: workerImage
          command: [
            'python'
            '-m'
            'app.worker'
          ]
          env: concat(commonEnvironment, [
            {
              name: 'WORKBENCH_OTEL_SERVICE_NAME'
              value: 'autodev-worker'
            }
          ])
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
        }
      ]
      scale: {
        minReplicas: workerMinReplicas
        maxReplicas: workerMaxReplicas
        rules: [
          {
            name: 'queued-executions'
            custom: {
              type: 'postgresql'
              metadata: {
                query: 'SELECT COUNT(*) FROM executionjob WHERE status = ''QUEUED'''
                targetQueryValue: '1'
              }
              auth: [
                {
                  secretRef: 'postgres-scale-connection'
                  triggerParameter: 'connection'
                }
              ]
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    api
  ]
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output containerAppsEnvironmentId string = environment.id
output keyVaultUrl string = keyVault.properties.vaultUri
output storageAccountUrl string = storage.properties.primaryEndpoints.blob
output workloadIdentityClientId string = workloadIdentity.properties.clientId
output workloadIdentityPrincipalId string = workloadIdentity.properties.principalId