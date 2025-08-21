name: Apply-to-eis-jumpbox-prodi-${{ inputs.env }}-vm

on:
  workflow_dispatch:
    inputs:
      version:
        description: "The version tag to deploy"
        required: true
      env:
        description: "Target environment (blue or green)"
        required: true
        default: blue

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  deploy:
    name: Deploy EIS-JUMPBOX-PROD1-${{ inputs.env }}-VM
    if: ${{ github.ref == 'refs/heads/main' && inputs.version != '' }}
    uses: dojo360/dojo-terraform-workflows/.github/workflows/pipeline-apply.yml@c6acd6cb6433896ef3d117ae4c4924708525cba2
    with:
      optumfile_path: "optumfiles/eastus/eis-jumpbox-prodi-${{ inputs.env }}.json"
      ref: ${{ inputs.version }}
      cloud_provider: "azure"
      azure_client_id: "7f7ac32c-39c2-4cce-a9c4-ed9d0869219c"
      azure_tenant_id: "db05faca-c829-40bd-b9c5-6ef0d6755421"
    secrets:
      AZ_CLIENT_SECRET: ${{ secrets.PDE_GVC_INTEGRATION_HUB_PROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.PDE_GHCC_PAT_SECRET }}

  destroy:
    name: Destroy EIS-JUMPBOX-PROD1-${{ inputs.env }}-VM
    if: ${{ github.ref == 'refs/heads/main' && inputs.version != '' }}
    uses: dojo360/dojo-terraform-workflows/.github/workflows/pipeline-destroy.yml@c6acd6cb6433896ef3d117ae4c4924708525cba2
    with:
      optumfile_path: "optumfiles/eastus/eis-jumpbox-prodi-${{ inputs.env }}.json"
      ref: ${{ inputs.version }}
      cloud_provider: "azure"
      azure_client_id: "7f7ac32c-39c2-4cce-a9c4-ed9d0869219c"
      azure_tenant_id: "db05faca-c829-40bd-b9c5-6ef0d6755421"
    secrets:
      AZ_CLIENT_SECRET: ${{ secrets.PDE_GVC_INTEGRATION_HUB_PROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.PDE_GHCC_PAT_SECRET }}