terraform {
  required_providers {
    splunk = {
      source  = "splunk/splunk"
      version = ">= 1.0.0"
    }
  }
}

provider "splunk" {
  url      = var.splunk_url
  username = var.splunk_username
  password = var.splunk_password
}



variable "splunk_url" {}
variable "splunk_username" {}
variable "splunk_password" {}



data "splunk_indexes" "all" {}

output "indexes" {
  value = data.splunk_indexes.all
}


