      - name: Extract service and VM details
        id: extract
        shell: bash
        run: |
          # Get the dimensions string (it's a string, not JSON)
          dims='${{ github.event.client_payload.dimensions }}'
          echo "Raw dimensions string: $dims"

          # Remove { and } if present
          clean_dims=$(echo "$dims" | sed 's/^{//; s/}$//')

          # Parse key=value pairs using awk
          service_name=$(echo "$clean_dims" | tr ',' '\n' | grep 'service_name=' | cut -d'=' -f2- | xargs)
          vm_name=$(echo "$clean_dims" | tr ',' '\n' | grep 'azure\.vm\.name=' | cut -d'=' -f2- | xargs)
          resource_group=$(echo "$clean_dims" | tr ',' '\n' | grep 'azure\.resourcegroup\.name=' | cut -d'=' -f2- | xargs)
          signal_value='${{ github.event.client_payload.signalValue }}'

          # Debug
          echo "service_name=$service_name"
          echo "vm_name=$vm_name"
          echo "resource_group=$resource_group"
          echo "signal_value=$signal_value"

          # Set outputs
          echo "service_name=$service_name" >> "$GITHUB_OUTPUT"
          echo "vm_name=$vm_name" >> "$GITHUB_OUTPUT"
          echo "resource_group=$resource_group" >> "$GITHUB_OUTPUT"
          echo "signal_value=$signal_value" >> "$GITHUB_OUTPUT"