# --- Required variables ---
$token = "ghp_yourPATtokenhere"     # FG-PAT with Actions: Write (or classic PAT with 'repo')
$org   = "your-github-org"
$repo  = "your-repo-name"

# EXACT workflow file name under .github/workflows OR the numeric workflow ID
$workflowFile = "your-workflow-file.yml"   # e.g., manage-vm.yml
$ref = "askid"                             # branch shown in your UI

# --- Headers ---
$headers = @{
  "Authorization"       = "Bearer $token"
  "Accept"              = "application/vnd.github+json"
  "X-GitHub-Api-Version"= "2022-11-28"
}

# --- Inputs that match your workflow_dispatch form ---
$body = @{
  ref    = $ref
  inputs = @{
    action               = "apply"
    target_environment   = "blue"
    vm_name              = "obser-qa-blue"
    windows_service_name = "ALG"
  }
} | ConvertTo-Json -Depth 5

# --- Dispatch the specific workflow with inputs ---
$uri = "https://api.github.com/repos/$org/$repo/actions/workflows/$workflowFile/dispatches"

Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -Body $body



{
  "ref": "askid",
  "inputs": {
    "action": "apply",
    "target_environment": "blue",
    "vm_name": "$result.host$",
    "windows_service_name": "$result.windows_service_name$"
  }
}


{
    "event_type": "splunk_alert",
    "client_payload": {
        "alert_name": "test_alert_from_windows",
        "severity": "info",
        "service": "demo",
        "host": "winserver01"
    }
} 
