# autoheal

jobs:
  aicicd:
    name: aicicd-poc
    uses: dojo360/dojo-terraform-workflows/.github/workflows/pipeline-apply.yml@cca6d6ccbd63896ef3d117ae4c492470852cb3c2
    needs: [read_optumfile]
    with:
      optumFilePath: "terraform/optumfiles/qa.json"
      cloud_provider: "azure"
      environment_name: qa
      azure_client_id: "${{ secrets.AZURE_CLIENT_ID }}"
      azure_tenant_id: "${{ secrets.AZURE_TENANT_ID }}"
    secrets:
      AZ_CLIENT_SECRET: "${{ secrets.PDE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}"
      GH_TOKEN: "${{ secrets.PDE_GHEC_PAT_SECRET }}"
    continue-on-error: true  # Allow workflow to continue even if aicicd fails

  capture_logs:
    name: Capture Logs if aicicd Fails
    needs: [aicicd]
    if: failure()  # Run only if aicicd fails
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Fetch Workflow Logs
        run: |
          mkdir -p logs
          echo "Fetching logs from aicicd..."
          gh run view ${{ github.run_id }} --log > logs/aicicd_error_log.txt || echo "Error log capture failed."
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}

      - name: Upload Error Logs
        uses: actions/upload-artifact@v3
        with:
          name: aicicd-error-log
          path: logs/aicicd_error_log.txt

  autoheal:
    name: Auto-Heal Deployment (if Terraform fails)
    needs: [capture_logs]
    if: failure()
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Download Terraform Error Log
        uses: actions/download-artifact@v3
        with:
          name: aicicd-error-log
          path: logs

      - name: Auto-Heal Deployment (if Terraform failed)
        run: |
          echo "Deployment failed. Running autoheal script..."
          echo "Captured Error Log:"
          cat logs/aicicd_error_log.txt
          
          python3 scripts/autoheal.py --error-log logs/aicicd_error_log.txt