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
          echo '${{ toJson(github.event.client_payload) }}' | jq .

      - name: Extract service and VM details
        id: extract
        shell: bash
        run: |
          dims='${{ toJson(github.event.client_payload.dimensions) }}'
          echo "Raw dimensions: $dims"

          service_name=$(echo "$dims" | jq -r '."service_name" // empty')
          vm_name=$(echo "$dims" | jq -r '."azure.vm.name" // empty')
          resource_group=$(echo "$dims" | jq -r '."azure.resourcegroup.name" // empty')
          signal_value='${{ github.event.client_payload.signalValue }}'

          echo "service_name=$service_name" >> "$GITHUB_OUTPUT"
          echo "vm_name=$vm_name" >> "$GITHUB_OUTPUT"
          echo "resource_group=$resource_group" >> "$GITHUB_OUTPUT"
          echo "signal_value=$signal_value" >> "$GITHUB_OUTPUT"