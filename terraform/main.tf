
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  client_id       = var.client_id
  tenant_id       = var.tenant_id
}

resource "azurerm_storage_account" "broken_storage" {
  name                     = "Invalid_Storage_Name"  # Error: Azure storage account names must be lowercase and alphanumeric
  resource_group_name      = "openai_rg"
  location                 = "East US"
  account_tier             = "InvalidTier"  # Error: Invalid SKU name
  account_replication_type = "LRS"
}

output "storage_endpoint" {
  value = azurerm_storage_account.broken_storage.primary_blob_endpoint
}
