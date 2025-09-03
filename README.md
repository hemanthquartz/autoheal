name: Apply-to-eis-jumpbox-qa-vm
run-name: Apply-to-eis-jumpbox-qa-vm

on:
  workflow_dispatch:
    inputs:
      action:
        description: "Action to perform"
        required: true
        default: apply
        type: choice
        options:
          - apply
          - destroy
      env:
        description: "Target environment"
        required: true
        default: blue
        type: choice
        options:
          - blue
          - green
      optstfville_path:
        description: "Terraform variables JSON path"
        required: true
        default: "equities/eis-jumpbox-${{ github.event.inputs.env }}.json"
      azure_client_id:
        description: "Azure Client ID"
        required: true
        default: "f0a3f0a2-b5eb-4767-86c8-bd813b8649a3"
      azure_tenant_id:
        description: "Azure Tenant ID"
        required: true
        default: "085f8aca-82fb-4bb0-8f68-cb6765754231"

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  deploy:
    name: Deploy EIS-JUMPBOX-QA-${{ inputs.env }}-VM
    if: ${{ github.ref == 'refs/heads/main' && github.event.inputs.action == 'apply' }}
    uses: ./.github/workflows/pipeline-apply.yml
    with:
      optstfville_path: "equities/eis-jumpbox-${{ inputs.env }}.json"
      cloud_providers: "azure"
      azure_client_id: ${{ github.event.inputs.azure_client_id }}
      azure_tenant_id: ${{ github.event.inputs.azure_tenant_id }}
      AZ_CLIENT_SECRET: ${{ secrets.PDE_SVC_INTEGRATOR_IAM_NONPROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.PDE_GHE_PAT_SECRET }}

  destroy:
    name: Destroy EIS-JUMPBOX-QA-${{ inputs.env }}-VM
    if: ${{ github.ref == 'refs/heads/main' && github.event.inputs.action == 'destroy' }}
    uses: ./.github/workflows/pipeline-destroy.yml
    with:
      optstfville_path: "equities/eis-jumpbox-${{ inputs.env }}.json"
      cloud_providers: "azure"
      azure_client_id: ${{ github.event.inputs.azure_client_id }}
      azure_tenant_id: ${{ github.event.inputs.azure_tenant_id }}
      AZ_CLIENT_SECRET: ${{ secrets.PDE_SVC_INTEGRATOR_IAM_NONPROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.PDE_GHE_PAT_SECRET }}