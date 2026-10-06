@description('Azure region for the session pool and monitoring resources.')
param location string = resourceGroup().location

@minLength(3)
@maxLength(63)
@description('Lowercase alphanumeric session pool name.')
param sessionPoolName string

@description('Resource ID of an existing Azure Container Apps managed environment.')
param containerAppsEnvironmentId string

@description('Full image reference for docker/azure-session, pinned by digest in production.')
param sessionImage string

@description('Azure Container Registry host, for example contoso.azurecr.io.')
param registryServer string

@description('User-assigned identity resource ID with AcrPull on the registry.')
param registryIdentityResourceId string

@allowed([
  'EgressDisabled'
  'EgressEnabled'
])
param networkStatus string = 'EgressDisabled'

@minValue(0)
param readySessionInstances int = 1

@minValue(1)
param maxConcurrentSessions int = 20

@minValue(60)
@maxValue(3600)
param cooldownPeriodInSeconds int = 300

@minValue(1)
param cpuCores int = 2

@description('Container memory such as 2Gi.')
param memory string = '2Gi'

@description('Log Analytics retention in days.')
@minValue(30)
param logRetentionDays int = 30

param tags object = {}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${sessionPoolName}-logs'
  location: location
  tags: tags
  properties: {
    retentionInDays: logRetentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource sessionPool 'Microsoft.App/sessionPools@2025-07-01' = {
  name: sessionPoolName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${registryIdentityResourceId}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironmentId
    containerType: 'CustomContainer'
    poolManagementType: 'Dynamic'
    scaleConfiguration: {
      maxConcurrentSessions: maxConcurrentSessions
      readySessionInstances: readySessionInstances
    }
    dynamicPoolConfiguration: {
      lifecycleConfiguration: {
        lifecycleType: 'Timed'
        cooldownPeriodInSeconds: cooldownPeriodInSeconds
      }
    }
    sessionNetworkConfiguration: {
      status: networkStatus
    }
    customContainerTemplate: {
      registryCredentials: {
        server: registryServer
        identity: registryIdentityResourceId
      }
      ingress: {
        targetPort: 8080
      }
      containers: [
        {
          name: 'autodev-session'
          image: sessionImage
          resources: {
            cpu: cpuCores
            memory: memory
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/ready'
                port: 8080
                scheme: 'HTTP'
              }
              periodSeconds: 5
              timeoutSeconds: 2
              failureThreshold: 30
              successThreshold: 1
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 15
              timeoutSeconds: 2
              failureThreshold: 3
              successThreshold: 1
            }
          ]
        }
      ]
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'session-pool-logs'
  scope: sessionPool
  properties: {
    workspaceId: logs.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource readyCapacityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (readySessionInstances > 0) {
  name: '${sessionPoolName}-no-ready-sessions'
  location: 'global'
  tags: tags
  properties: {
    description: 'The Autodev session pool has no ready session capacity.'
    severity: 2
    enabled: true
    scopes: [sessionPool.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    autoMitigate: true
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'NoReadySessions'
          metricNamespace: 'Microsoft.App/sessionPools'
          metricName: 'PoolReadyPodCount'
          operator: 'LessThan'
          threshold: 1
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: []
  }
}

output sessionPoolId string = sessionPool.id
output sessionPoolEndpoint string = sessionPool.properties.poolManagementEndpoint
output logAnalyticsWorkspaceId string = logs.id