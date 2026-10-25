targetScope = 'resourceGroup'

param sessionPoolName string
param principalId string
param principalType string = 'ServicePrincipal'
param roleDefinitionId string

resource sessionPool 'Microsoft.App/sessionPools@2025-07-01' existing = {
  name: sessionPoolName
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sessionPool.id, principalId, roleDefinitionId)
  scope: sessionPool
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}
