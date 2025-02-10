plaintext
Error: name ("Invalid_Storage_Name") can only consist of lowercase letters and numbers, and must be between 3 and 24 characters long
on main.tf line 10, in resource "azurerm_storage_account" "broken_storage":
10:   name = "Invalid_Storage_Name"
