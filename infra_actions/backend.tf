terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "tfstatefab086b0"
    container_name       = "tfstate" # <--- Ensure this matches exactly!
    key                  = "terraform.tfstate"
    use_azuread_auth     = true
  }
}