name: VM Ops

on:
  workflow_dispatch:
    inputs:
      action:
        description: "What to do"
        required: true
        type: choice
        options: [restart_service]
      subscription_id:
        description: "Azure Subscription ID"
        required: true
      resource_group:
        description: "VM Resource Group"
        required: true
      vm_name:
        description: "VM Name"
        required: true
      service_name:
        description: "Windows service name (e.g., MSSQLSERVER)"
        required: true

jobs:
  restart-service:
    if: ${{ inputs.action == 'restart_service' }}
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - name: Azure login (OIDC)
        uses: azure/login@v2
        with:
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ inputs.subscription_id }}

      - name: Restart service on VM
        uses: azure/CLI@v1
        with:
          inlineScript: |
            az account set --subscription "${{ inputs.subscription_id }}"
            az vm run-command invoke \
              --resource-group "${{ inputs.resource_group }}" \
              --name "${{ inputs.vm_name }}" \
              --command-id RunPowerShellScript \
              --scripts "Restart-Service -Name '${{ inputs.service_name }}' -Force; Get-Service -Name '${{ inputs.service_name }}'"