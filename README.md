name: Splunk Alert Handler

on:
  repository_dispatch:
    types: [splunk_alert, splunk_search_alert, splunk_observability_alert]

jobs:
  handle:
    runs-on: uhg-runner

    outputs:
      service_name:   ${{ steps.extract.outputs.service_name }}
      vm_name:        ${{ steps.extract.outputs.vm_name }}
      resource_group: ${{ steps.extract.outputs.resource_group }}
      signal_value:   ${{ steps.extract.outputs.signal_value }}

    steps:
      - name: Show raw payload (for debugging)
        run: |
          echo "Action: ${{ github.event.action }}"
          echo "Client payload:"
          echo '${{ toJson(github.event.client_payload) }}'

      - name: Extract service / VM / RG from dimensions
        id: extract
        shell: bash
        run: |
          # from payload: "dimensions": "{azure.vm.size=..., service_name=..., azure.resourcegroup.name=..., azure.vm.name=..., ...}"
          dims='${{ github.event.client_payload.dimensions }}'
          echo "Raw dimensions: $dims"

          # Parse values out of the dimensions string
          service_name=$(echo "$dims" | sed -n 's/.*service_name=\([^,}]*\).*/\1/p')
          vm_name=$(echo "$dims" | sed -n 's/.*azure\.vm\.name=\([^,}]*\).*/\1/p')
          resource_group=$(echo "$dims" | sed -n 's/.*azure\.resourcegroup\.name=\([^,}]*\).*/\1/p')

          echo "Parsed service_name=$service_name"
          echo "Parsed vm_name=$vm_name"
          echo "Parsed resource_group=$resource_group"

          echo "service_name=$service_name"   >> "$GITHUB_OUTPUT"
          echo "vm_name=$vm_name"             >> "$GITHUB_OUTPUT"
          echo "resource_group=$resource_group" >> "$GITHUB_OUTPUT"

          # from payload: "signalValue": "4"
          echo "signal_value=${{ github.event.client_payload.signalValue }}" >> "$GITHUB_OUTPUT"

  restart-service:
    needs: handle

    # Only restart when signalValue exists and < 4 (skip when == 4)
    if: ${{ needs.handle.outputs.signal_value != '' && fromJson(needs.handle.outputs.signal_value) < 4 }}

    runs-on: uhg-runner
    permissions:
      id-token: write
      contents: read

    # Modular: everything driven by env vars
    env:
      AZURE_SUBSCRIPTION_ID: 5204df69-30ab-4345-a9d2-ddb0ac139a3c
      SERVICE_NAME:   ${{ needs.handle.outputs.service_name }}
      VM_NAME:        ${{ needs.handle.outputs.vm_name }}
      RESOURCE_GROUP: ${{ needs.handle.outputs.resource_group }}

    steps:
      - name: Azure Login
        uses: azure/login@v2
        with:
          creds: >
            {"clientId":"e976a6f2-bb3f-4767-86c8-e18b3136b843",
             "clientSecret":"${{ secrets.PDE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}",
             "subscriptionId":"${{ env.AZURE_SUBSCRIPTION_ID }}",
             "tenantId":"db05faca-c82a-4b9d-b9c5-0f64b6755421"}

      - name: Restart service on VM (modular)
        uses: azure/CLI@v1
        with:
          inlineScript: |
            echo "signalValue=${{ needs.handle.outputs.signal_value }}"
            echo "Restarting '$SERVICE_NAME' on VM '$VM_NAME' in RG '$RESOURCE_GROUP'"

            az account set --subscription "$AZURE_SUBSCRIPTION_ID"

            az vm run-command invoke \
              --resource-group "$RESOURCE_GROUP" \
              --name "$VM_NAME" \
              --command-id RunPowerShellScript \
              --scripts "Restart-Service -Name '$SERVICE_NAME' -Force; Get-Service -Name '$SERVICE_NAME'"