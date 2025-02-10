hcl
resource "azurerm_storage_account" "broken_storage" {
  name                     = "validstoragename123" # Must be lowercase and between 3-24 characters
  resource_group_name      = azurerm_resource_group.example.name
  location                 = azurerm_resource_group.example.location
  account_tier             = "Standard" # Must be either "Standard" or "Premium"
  account_replication_type = "LRS"
}