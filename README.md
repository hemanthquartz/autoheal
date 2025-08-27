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

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  deploy:
    if: ${{ github.event.inputs.action == 'apply' }}
    name: Deploy EIS-JUMPBOX-QA-${{ github.event.inputs.env }}-VM
    uses: djo360e/dojoterraform-workflows/.github/workflows/pipeline-apply.yml@c2ac6d0cb6438869ef3d117ae4c492
    with:
      optumfile_path: "optumfiles/eastus/eis-jumpbox-qa-${{ github.event.inputs.env }}.json"
      cloud_provider: "azure"
      azure_client_id: "e9706af2-bb3f-4767-86c8-e1bb13b6b843"
      azure_tenant_id: "db05afca-c82a-4b9d-b9c5-6f6ab6755421"
    secrets:
      AZ_CLIENT_SECRET: ${{ secrets.POE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.POE_GHEC_PAT_SECRET }}

  destroy:
    if: ${{ github.event.inputs.action == 'destroy' }}
    name: Destroy EIS-JUMPBOX-QA-${{ github.event.inputs.env }}-VM
    uses: djo360e/dojoterraform-workflows/.github/workflows/pipeline-destroy.yml@c2ac6d0cb6438869ef3d117ae4c492
    with:
      optumfile_path: "optumfiles/eastus/eis-jumpbox-qa-${{ github.event.inputs.env }}.json"
      cloud_provider: "azure"
      azure_client_id: "e9706af2-bb3f-4767-86c8-e1bb13b6b843"
      azure_tenant_id: "db05afca-c82a-4b9d-b9c5-6f6ab6755421"
    secrets:
      AZ_CLIENT_SECRET: ${{ secrets.POE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.POE_GHEC_PAT_SECRET }}