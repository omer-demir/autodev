@description('Azure region for the family demo resources.')
param location string = resourceGroup().location

@minLength(5)
@maxLength(18)
@description('Lowercase prefix used to derive globally unique resource names.')
param namePrefix string = 'autodev-family'

@description('Public Cloudflare hostname, without a scheme.')
param customDomain string

@secure()
@description('Token for a remotely managed Cloudflare Tunnel. Configure its public hostname to use http://gateway:8080.')
param cloudflareTunnelToken string

@description('Existing Azure Container Registry name containing the API and web images.')
param registryName string

@description('Resource group containing the existing Azure Container Registry.')
param registryResourceGroupName string = resourceGroup().name

@description('Subscription containing the existing Azure Container Registry.')
param registrySubscriptionId string = subscription().subscriptionId

@description('API image pinned by digest, for example registry.azurecr.io/autodev-api@sha256:...')
param apiImage string

@description('Web image pinned by digest. Build it with an empty NEXT_PUBLIC_API_URL and WORKBENCH_API_URL=http://api:8000.')
param webImage string

@description('Existing Azure Container Apps dynamic session pool name.')
param sessionPoolName string

@description('Resource group containing the dynamic session pool.')
param sessionPoolResourceGroupName string = resourceGroup().name

@description('Subscription containing the dynamic session pool.')
param sessionPoolSubscriptionId string = subscription().subscriptionId

@description('Dynamic session pool management endpoint emitted by infra/azure/main.bicep.')
param sessionPoolEndpoint string

@description('Role definition GUID for Azure ContainerApps Session Executor in this tenant.')
param sessionExecutorRoleDefinitionId string

@allowed([
  'none'
  'bridge'
])
@description('Must match the immutable egress configuration of the selected session pool.')
param sessionPoolNetworkMode string = 'none'

@description('Microsoft Foundry project Responses endpoint.')
param foundryResponsesEndpoint string

@description('Default deployed Foundry model name.')
param foundryDefaultModel string

@description('Foundry deployed model names displayed by AutoDev. The default model is added automatically if omitted.')
param foundryModels array = []

@description('Optional existing Microsoft Foundry/Cognitive Services account name. When set, the VM receives the supplied model invocation role and a private endpoint is created.')
param foundryAccountName string = ''

@description('Resource group containing the existing Foundry account.')
param foundryAccountResourceGroupName string = resourceGroup().name

@description('Subscription containing the existing Foundry account.')
param foundryAccountSubscriptionId string = subscription().subscriptionId

@description('Foundry model invocation role definition GUID. Required when foundryAccountName is set.')
param foundryRoleDefinitionId string = ''

@description('Microsoft Entra tenant ID used for family sign-in.')
param tenantId string = tenant().tenantId

@description('Microsoft Entra application client ID.')
param oidcClientId string

@description('Expected OIDC audience. For Entra this is normally the application client ID or its Application ID URI.')
param oidcAudience string

@secure()
@description('Microsoft Entra application client secret.')
param oidcClientSecret string

@secure()
@description('URL-safe PostgreSQL password for the local VM database.')
param postgresPassword string

@secure()
@description('Stable high-entropy key used only as a compatibility fallback for encrypted database credentials.')
param credentialMasterKey string

@description('Linux administrator username. The VM has no public IP and accepts no inbound traffic.')
param adminUsername string = 'azureuser'

@description('SSH public key retained for private-network recovery access.')
param adminSshPublicKey string

@description('Cost-conscious VM size. Standard_B2as_v2 provides 2 vCPU and 8 GiB RAM in supported regions.')
param vmSize string = 'Standard_B2as_v2'

@minValue(64)
@description('Premium OS disk size in GiB. Application data and the local database are stored on this disk.')
param osDiskSizeGb int = 128

@allowed([
  'defaultOutbound'
  'natGateway'
])
@description('defaultOutbound avoids a NAT Gateway charge. Use natGateway when the region/subscription does not permit explicit default outbound access.')
param outboundConnectivity string = 'defaultOutbound'

@description('PostgreSQL image used by the VM Compose stack.')
param postgresImage string = 'postgres:17-alpine'

@description('Redis image used by the VM Compose stack.')
param redisImage string = 'redis:7.4-alpine'

@description('Caddy image used as the private HTTP gateway.')
param gatewayImage string = 'caddy:2.10-alpine'

@description('Cloudflare Tunnel image. Pin this to a tested immutable digest before long-term use.')
param cloudflaredImage string = 'cloudflare/cloudflared:latest'

@description('Tags applied to all supported resources.')
param tags object = {
  workload: 'autodev'
  environment: 'family-demo'
}

var token = uniqueString(subscription().id, resourceGroup().id, namePrefix)
var vmName = take('${namePrefix}-vm', 64)
var vnetName = take('${namePrefix}-vnet', 64)
var storageName = take(toLower(replace('${namePrefix}${token}', '-', '')), 24)
var keyVaultName = take(toLower('${namePrefix}-${token}-kv'), 24)
var useNatGateway = outboundConnectivity == 'natGateway'
var allFoundryModels = union([foundryDefaultModel], foundryModels)
var entraLoginEndpoint = environment().authentication.loginEndpoint
var oidcIssuer = '${entraLoginEndpoint}${tenantId}/v2.0'
var oidcAuthorizationUrl = '${entraLoginEndpoint}${tenantId}/oauth2/v2.0/authorize'
var oidcTokenUrl = '${entraLoginEndpoint}${tenantId}/oauth2/v2.0/token'
var oidcJwksUrl = '${entraLoginEndpoint}${tenantId}/discovery/v2.0/keys'
var webAppUrl = 'https://${customDomain}'
var blobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (!empty(foundryAccountName)) {
  scope: resourceGroup(foundryAccountSubscriptionId, foundryAccountResourceGroupName)
  name: foundryAccountName
}

resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${namePrefix}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 4000
          access: 'Deny'
          direction: 'Inbound'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = if (useNatGateway) {
  name: '${namePrefix}-nat-pip'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2024-05-01' = if (useNatGateway) {
  name: '${namePrefix}-nat'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 10
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
  }
}

resource vmSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'control-plane'
  properties: union({
    addressPrefix: '10.42.1.0/24'
    defaultOutboundAccess: !useNatGateway
    networkSecurityGroup: {
      id: nsg.id
    }
  }, useNatGateway ? {
    natGateway: {
      id: natGateway.id
    }
  } : {})
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'private-endpoints'
  properties: {
    addressPrefix: '10.42.2.0/24'
    defaultOutboundAccess: false
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  #disable-next-line BCP334
  name: storageName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
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

resource backupContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'autodev-backups'
  properties: {
    publicAccess: 'None'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 14
    enabledForTemplateDeployment: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'None'
      defaultAction: 'Deny'
    }
  }
}

resource cloudflareTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cloudflare-tunnel-token'
  properties: {
    value: cloudflareTunnelToken
  }
}

resource postgresPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'postgres-password'
  properties: {
    value: postgresPassword
  }
}

resource credentialMasterKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'credential-master-key'
  properties: {
    value: credentialMasterKey
  }
}

resource oidcClientSecretResource 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'oidc-client-secret'
  properties: {
    value: oidcClientSecret
  }
}

resource blobPrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  #disable-next-line no-hardcoded-env-urls
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
  tags: tags
}

resource blobPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: blobPrivateDns
  name: '${namePrefix}-blob-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${namePrefix}-blob-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource storagePrivateDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: storagePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: blobPrivateDns.id
        }
      }
    ]
  }
}

resource vaultPrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource vaultPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: vaultPrivateDns
  name: '${namePrefix}-vault-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource vaultPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: '${namePrefix}-vault-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'vault'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource vaultPrivateDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: vaultPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vault'
        properties: {
          privateDnsZoneId: vaultPrivateDns.id
        }
      }
    ]
  }
}

resource foundryServicesPrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = if (!empty(foundryAccountName)) {
  name: 'privatelink.services.ai.azure.com'
  location: 'global'
  tags: tags
}

resource foundryCognitivePrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = if (!empty(foundryAccountName)) {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource foundryOpenAiPrivateDns 'Microsoft.Network/privateDnsZones@2024-06-01' = if (!empty(foundryAccountName)) {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

resource foundryServicesPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!empty(foundryAccountName)) {
  parent: foundryServicesPrivateDns
  name: '${namePrefix}-foundry-services-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource foundryCognitivePrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!empty(foundryAccountName)) {
  parent: foundryCognitivePrivateDns
  name: '${namePrefix}-foundry-cognitive-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource foundryOpenAiPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!empty(foundryAccountName)) {
  parent: foundryOpenAiPrivateDns
  name: '${namePrefix}-foundry-openai-link'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource foundryPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (!empty(foundryAccountName)) {
  name: '${namePrefix}-foundry-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'foundry-account'
        properties: {
          privateLinkServiceId: foundryAccount.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource foundryPrivateDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (!empty(foundryAccountName)) {
  parent: foundryPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'services-ai'
        properties: {
          privateDnsZoneId: foundryServicesPrivateDns.id
        }
      }
      {
        name: 'cognitive-services'
        properties: {
          privateDnsZoneId: foundryCognitivePrivateDns.id
        }
      }
      {
        name: 'openai'
        properties: {
          privateDnsZoneId: foundryOpenAiPrivateDns.id
        }
      }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: '${vmName}-nic'
  location: location
  tags: tags
  properties: {
    enableAcceleratedNetworking: false
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: vmSubnet.id
          }
        }
      }
    ]
  }
}

var bootstrap00 = loadTextContent('./family-demo/bootstrap.sh')
var bootstrap01 = replace(bootstrap00, '__REGISTRY_NAME__', registryName)
var bootstrap02 = replace(bootstrap01, '__KEY_VAULT_NAME__', keyVault.name)
var bootstrap03 = replace(bootstrap02, '__STORAGE_ACCOUNT_NAME__', storage.name)
var bootstrap04 = replace(bootstrap03, '__API_IMAGE__', apiImage)
var bootstrap05 = replace(bootstrap04, '__WEB_IMAGE__', webImage)
var bootstrap06 = replace(bootstrap05, '__POSTGRES_IMAGE__', postgresImage)
var bootstrap07 = replace(bootstrap06, '__REDIS_IMAGE__', redisImage)
var bootstrap08 = replace(bootstrap07, '__GATEWAY_IMAGE__', gatewayImage)
var bootstrap09 = replace(bootstrap08, '__CLOUDFLARED_IMAGE__', cloudflaredImage)
var bootstrap10 = replace(bootstrap09, '__CUSTOM_DOMAIN__', customDomain)
var bootstrap11 = replace(bootstrap10, '__FOUNDRY_ENDPOINT__', foundryResponsesEndpoint)
var bootstrap12 = replace(bootstrap11, '__FOUNDRY_DEFAULT_MODEL__', foundryDefaultModel)
var bootstrap13 = replace(bootstrap12, '__FOUNDRY_MODELS__', join(allFoundryModels, ','))
var bootstrap14 = replace(bootstrap13, '__SESSION_POOL_ENDPOINT__', sessionPoolEndpoint)
var bootstrap15 = replace(bootstrap14, '__SESSION_POOL_NETWORK_MODE__', sessionPoolNetworkMode)
var bootstrap16 = replace(bootstrap15, '__OIDC_ISSUER__', oidcIssuer)
var bootstrap17 = replace(bootstrap16, '__OIDC_AUDIENCE__', oidcAudience)
var bootstrap18 = replace(bootstrap17, '__OIDC_JWKS_URL__', oidcJwksUrl)
var bootstrap19 = replace(bootstrap18, '__OIDC_AUTHORIZATION_URL__', oidcAuthorizationUrl)
var bootstrap20 = replace(bootstrap19, '__OIDC_TOKEN_URL__', oidcTokenUrl)
var bootstrap21 = replace(bootstrap20, '__OIDC_CLIENT_ID__', oidcClientId)
var bootstrap22 = replace(bootstrap21, '__WEB_APP_URL__', webAppUrl)

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: vmName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        diskSizeGB: osDiskSizeGb
        managedDisk: {
          storageAccountType: 'Premium_LRS'
        }
      }
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      customData: base64(bootstrap22)
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        patchSettings: {
          assessmentMode: 'AutomaticByPlatform'
          patchMode: 'AutomaticByPlatform'
        }
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminSshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            primary: true
          }
        }
      ]
    }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: {
        secureBootEnabled: true
        vTpmEnabled: true
      }
    }
  }
}

resource vmBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, vm.id, blobDataContributorRoleId)
  scope: storage
  properties: {
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributorRoleId)
  }
}

resource vmVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, vm.id, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
  }
}

module vmRegistryRole './family-demo/acr-pull-role.bicep' = {
  name: 'vm-acr-pull-${token}'
  scope: resourceGroup(registrySubscriptionId, registryResourceGroupName)
  params: {
    registryName: registryName
    principalId: vm.identity.principalId
  }
}

module vmSessionExecutorRole './family-demo/session-executor-role.bicep' = {
  name: 'vm-session-executor-${token}'
  scope: resourceGroup(sessionPoolSubscriptionId, sessionPoolResourceGroupName)
  params: {
    sessionPoolName: sessionPoolName
    principalId: vm.identity.principalId
    roleDefinitionId: sessionExecutorRoleDefinitionId
  }
}

module vmFoundryRole './family-demo/foundry-role.bicep' = if (!empty(foundryAccountName) && !empty(foundryRoleDefinitionId)) {
  name: 'vm-foundry-${token}'
  scope: resourceGroup(foundryAccountSubscriptionId, foundryAccountResourceGroupName)
  params: {
    foundryAccountName: foundryAccountName
    principalId: vm.identity.principalId
    roleDefinitionId: foundryRoleDefinitionId
  }
}

output vmId string = vm.id
output vmPrincipalId string = vm.identity.principalId
output vmPrivateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
output storageAccountName string = storage.name
output storageAccountUrl string = storage.properties.primaryEndpoints.blob
output keyVaultName string = keyVault.name
output keyVaultUrl string = keyVault.properties.vaultUri
output cloudflareOriginService string = 'http://gateway:8080'
output applicationUrl string = webAppUrl
output foundryRoleConfigured bool = !empty(foundryAccountName) && !empty(foundryRoleDefinitionId)
