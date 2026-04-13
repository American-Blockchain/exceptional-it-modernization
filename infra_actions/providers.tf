# ---------------------------------------------------------
# Provider Configuration
# ---------------------------------------------------------

provider "azurerm" {
  # The features block is mandatory for the AzureRM provider (v2.0+)
  # Even if empty, it must be present to satisfy the provider's schema.
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }

  # These values can be optionally set here, but they are typically 
  # inherited from the environment or CLI (az login / SPN env vars)
  # subscription_id = var.subscription_id 
}
