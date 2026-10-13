using './control-plane.bicep'

param location = 'eastus2'
param namePrefix = 'autodev'
param apiImage = 'autodev.azurecr.io/autodev-api@sha256:replace-me'
param registryServer = 'autodev.azurecr.io'
param registryIdentityResourceId = '/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/autodev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/autodev-pull'
param sessionPoolName = 'autodevsessions'
param sessionPoolEndpoint = 'https://replace-me.dynamicsessions.io'
param sessionExecutorRoleDefinitionId = '00000000-0000-0000-0000-000000000000'
param postgresAdminPassword = readEnvironmentVariable('AUTODEV_POSTGRES_ADMIN_PASSWORD')
param foundryResponsesEndpoint = 'https://replace-me.services.ai.azure.com/api/projects/replace-me'
param authMode = 'oidc'
param oidcIssuer = 'https://login.microsoftonline.com/replace-me/v2.0'
param oidcAudience = 'api://autodev'
param oidcJwksUrl = 'https://login.microsoftonline.com/replace-me/discovery/v2.0/keys'
param githubOAuthClientId = readEnvironmentVariable('AUTODEV_GITHUB_OAUTH_CLIENT_ID', '')
param githubOAuthClientSecret = readEnvironmentVariable('AUTODEV_GITHUB_OAUTH_CLIENT_SECRET', '')
param webAppUrl = 'https://replace-me.example.com'