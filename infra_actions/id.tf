# 1. Create the Azure Container Registry
resource "azurerm_container_registry" "acr" {
  name                          = var.acr_name
  resource_group_name           = data.azurerm_resource_group.rg.name
  location                      = data.azurerm_resource_group.rg.location
  sku                           = "Premium" # Required for Network Rule Sets
  admin_enabled                 = false      # Disabled for security; we use Managed Identity
  public_network_access_enabled = true       # Set to true but controlled by network_rule_set

  network_rule_bypass_option    = "AzureServices"

  network_rule_set {
    default_action = "Allow" # Set to Allow for GitHub Actions build-to-push compatibility unless on Private Runners
  }
}

# 2. Create the User-Assigned Managed Identity for GitHub Actions
resource "azurerm_user_assigned_identity" "github_actions_identity" {
  name                = var.identity_name
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
}

# 3. Grant the Identity "AcrPush" rights to the Registry
resource "azurerm_role_assignment" "acr_push" {
  principal_id         = azurerm_user_assigned_identity.github_actions_identity.principal_id
  role_definition_name = "AcrPush"
  scope                = azurerm_container_registry.acr.id
}

# 4. Establish the OIDC Trust (Federated Identity Credential)
resource "azurerm_federated_identity_credential" "github_oidc" {
  name                = var.federated_credential_name
  resource_group_name = data.azurerm_resource_group.rg.name
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  parent_id           = azurerm_user_assigned_identity.github_actions_identity.id
  
  # CRITICAL: This dictates EXACTLY which GitHub repo and branch can assume this identity
  subject             = var.github_subject
}

resource "azurerm_federated_identity_credential" "github_oidc_bass" {
  name                = "github-actions-bass-branch"
  resource_group_name = data.azurerm_resource_group.rg.name
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  parent_id           = azurerm_user_assigned_identity.github_actions_identity.id
  subject             = "repo:American-Blockchain/exceptional-it-modernization:ref:refs/heads/bass"
}

# Output these values; you will need them for your GitHub Actions Variables
output "AZURE_CLIENT_ID" { value = azurerm_user_assigned_identity.github_actions_identity.client_id }
output "AZURE_TENANT_ID" { value = data.azurerm_client_config.current.tenant_id }
output "AZURE_SUBSCRIPTION_ID" { value = data.azurerm_client_config.current.subscription_id }
output "ACR_NAME" { value = azurerm_container_registry.acr.name }