@description('Azure region for the family demo build registry and dynamic session environment.')
param location string = resourceGroup().location

@minLength(5)
@maxLength(18)
param namePrefix string = 'autodev-family'

@description('Log Analytics retention in days.')
@minValue(30)
param logRetentionDays int = 30

param tags object = {
  workload: 'autodev'
  environment: 'family-demo'
}

var token = uniqueString(subscription().id, resourceGroup().id, namePrefix)
var registryName = take(toLower(replace('${namePrefix}${token}acr', '-', '')), 50)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  #disable-next-line BCP334
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource sessionPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-session-pull'
  location: location
  tags: tags
}

resource sessionPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, sessionPullIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: sessionPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

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
  name: '${namePrefix}-sessions-env'
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
    zoneRedundant: false
  }
}

output registryName string = registry.name
output registryServer string = registry.properties.loginServer
output registryResourceId string = registry.id
output sessionPullIdentityResourceId string = sessionPullIdentity.id
output sessionPullIdentityClientId string = sessionPullIdentity.properties.clientId
output containerAppsEnvironmentId string = environment.id
output logAnalyticsWorkspaceId string = logs.id
