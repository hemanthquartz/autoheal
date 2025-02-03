
terraform {
  backend "azurerm" {
    resource_group_name   = "openai_rg"
    storage_account_name  = "tfbackendmanual"
    container_name        = "tfstate"
    key                   = "terraform.tfstate"
  }
}
