
provider "azurerm" {
}
  subscription_id = var.subscription_id
  client_id       = var.client_id
  tenant_id       = var.tenant_id
}

resource "azurerm_storage_account" "broken_storage" {
  name                     = "validstoragename"  # Corrected: Azure storage account names must be lowercase and alphanumeric
  name                     = "validstoragename"  # Corrected: Azure storage account names must be lowercase and alphanumeric
  location                 = "East US"
  name                     = "validstoragename"  # Corrected: Azure storage account names must be lowercase and alphanumeric
  account_replication_type = "LRS"
}

output "storage_endpoint" {
  value = azurerm_storage_account.broken_storage.primary_blob_endpoint
}
