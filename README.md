name: Auto-Healing Deployment Pipeline

on:
  workflow_dispatch:

permissions:
  id-token: write
  contents: write
  pull-requests: write

jobs:
  read_optumfile:
    name: Read Optumfile
    uses: dojo360/dojo-terraform-workflows/.github/workflows/read-optumfile.yml@cca60dc6b438869ef3d117ae4c492470852cb3c2 # v2.0.4
    with:
      file_path: "terraform/optumfiles/qa.json"
      cloud_provider: "azure"
      azure_client_id: "e976a6f2-bb3f-4767-86c8-e18b3136b843"
      azure_tenant_id: "db05faca-c82a-4b9d-b9c5-0f64b6755421"
    # secrets:
    #   AZ_CLIENT_SECRET: ${{ secrets.PDE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}

  aicicd:
    name: aicicd-poc
    uses: dojo360/dojo-terraform-workflows/.github/workflows/pipeline-apply.yml@cca60dc6b438869ef3d117ae4c492470852cb3c2 # v2.0.4
    needs: [read_optumfile]
    with:
      optumfile_path: "terraform/optumfiles/qa.json"
      cloud_provider: "azure"
      environment_name: ""
      azure_client_id: "e976a6f2-bb3f-4767-86c8-e18b3136b843"
      azure_tenant_id: "db05faca-c82a-4b9d-b9c5-0f64b6755421"
    run: |
      echo "Running aicicd-poc.."

    secrets:
      # AZ_CLIENT_SECRET: ${{ secrets.PDE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}
      GH_TOKEN: ${{ secrets.PDE_GHEC_PAT_SECRET }}

  capture_job_id:
    name: Capture aicicd Job ID
    runs-on: ubuntu-latest
    needs: [aicicd]
    steps:
      - name: Get Workflow Run Jobs
        run: |
          JOBS=$(gh api repos/${{ github.repository }}/actions/runs/${{ github.run_id }}/jobs --jq '.jobs[] | select(.name=="aicicd-poc") | .id')
          echo "AICICD_JOB_ID=$JOBS" >> $GITHUB_ENV
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Fetch aicicd Logs
        run: |
          echo "Fetching logs for Job ID: $AICICD_JOB_ID"
          gh api repos/${{ github.repository }}/actions/jobs/$AICICD_JOB_ID/logs
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
