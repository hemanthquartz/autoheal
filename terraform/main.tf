
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  client_id       = var.client_id
  tenant_id       = var.tenant_id
}

resource "azurerm_storage_account" "broken_storage" {
  name                     = "validstoragename01" # Corrected: Must be lowercase and alphanumeric between 3 and 24 characters
  resource_group_name      = "openai_rg"
  location                 = "East US"
  account_tier             = "Standard" # Corrected: Must be either "Standard" or "Premium"
  account_replication_type = "LRS"
}

output "storage_endpoint" {
  value = azurerm_storage_account.broken_storage.primary_blob_endpoint
}
