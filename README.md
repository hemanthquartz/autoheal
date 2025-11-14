      - name: Extract service / VM / RG from dimensions
        id: extract
        shell: bash
        run: |
          dims='${{ github.event.client_payload.dimensions }}'

          # Correct field names from the payload image
          service_name=$(echo "$dims" | sed -n 's/.*service_name=\([^,}]*\).*/\1/p')
          vm_name=$(echo "$dims" | sed -n 's/.*azure\.vm\.name=\([^,}]*\).*/\1/p')
          resource_group=$(echo "$dims" | sed -n 's/.*cloud\.resourcegroup\.name=\([^,}]*\).*/\1/p')

          echo "Parsed service_name=$service_name"
          echo "Parsed vm_name=$vm_name"
          echo "Parsed resource_group=$resource_group"

          echo "service_name=$service_name"        >> "$GITHUB_OUTPUT"
          echo "vm_name=$vm_name"                  >> "$GITHUB_OUTPUT"
          echo "resource_group=$resource_group"    >> "$GITHUB_OUTPUT"

          echo "signal_value=${{ github.event.client_payload.signalValue }}" >> "$GITHUB_OUTPUT"