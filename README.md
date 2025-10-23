- name: Tool Installs
  uses: azure/CLI@v1
  with:
    inlineScript: |
      az login --service-principal -u "ed1f47ce-33c2-44ce-a9c4-e6d80862109c" -p "${{ secrets.PDE_SVC_INTEGRATION_HUB_NONPROD_CLIENT_SECRET }}" --tenant "db05faca-c82a-4b9d-b9c5-0f64b6755421"
      az account set -s "0be4d12d-fd78-4531-b0e2-57dc76412d9"
      echo "az login completed"

      # Map inputs.env to env_short
      if [ "${{ inputs.env }}" = "blue" ]; then
        env_short="blu"
      elif [ "${{ inputs.env }}" = "green" ]; then
        env_short="grn"
      else
        echo "❌ Unsupported environment: ${{ inputs.env }}"
        exit 1
      fi

      echo "✅ Environment short name resolved to: $env_short"

      # Invoke RunPowerShellScript on correct VM name
      az vm run-command invoke \
        --resource-group "provider-integration-hub-jumpbox-eastus-rg-qa" \
        --name "eis-jbxprd1-${env_short}" \
        --command-id RunPowerShellScript \
        --scripts "
          Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

          Set-Service -Name sshd -StartupType Automatic
          Start-Service sshd

          Set-Service -Name ssh-agent -StartupType Automatic
          Start-Service ssh-agent

          Get-Service sshd

          if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
            Write-Output 'Firewall Rule OpenSSH-Server-In-TCP does not exist, creating it...'
            New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
              -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
          } else {
            Write-Output 'Firewall rule OpenSSH-Server-In-TCP already exists.'
          }
        "