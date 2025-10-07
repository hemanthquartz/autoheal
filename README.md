$token = "ghp_yourPATtokenhere"
$org = "your-github-org"
$repo = "your-repo-name"

$headers = @{
    "Authorization" = "Bearer $token"
    "Accept" = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$body = @{
    event_type = "splunk_alert"
    client_payload = @{
        alert_name = "test_alert_from_windows"
        severity   = "info"
        service    = "demo"
        host       = "winserver01"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "https://api.github.com/repos/$org/$repo/dispatches" `
                  -Method Post `
                  -Headers $headers `
                  -Body $body