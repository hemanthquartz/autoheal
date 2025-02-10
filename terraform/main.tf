hcl
resource "azurerm_storage_account" "broken_storage" {
  name                     = "validstoragename" # Must be lowercase, alphanumeric, and between 3-24 characters
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard" # Valid values are "Premium" or "Standard"
  account_replication_type = "LRS"
}