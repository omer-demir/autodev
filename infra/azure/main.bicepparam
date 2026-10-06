using './main.bicep'

param location = 'eastus2'
param sessionPoolName = 'autodevsessions'
param containerAppsEnvironmentId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/autodev/providers/Microsoft.App/managedEnvironments/autodev'
param sessionImage = 'autodev.azurecr.io/autodev-session:1.0.0'
param registryServer = 'autodev.azurecr.io'
param registryIdentityResourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/autodev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/autodev-session-pull'
param networkStatus = 'EgressDisabled'
param readySessionInstances = 1
param maxConcurrentSessions = 20