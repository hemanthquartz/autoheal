$AFD_HOST="<your-endpoint>.azurefd.net"  # or your custom domain
curl.exe -i -X POST "https://$AFD_HOST/splunk/dispatch" ^
  -H "Content-Type: application/json" ^
  -H "X-Webhook-Token: <shared-secret-if-enforced>" ^
  --data "{`"event_type`":`"splunk_alert`",`"client_payload`":{`"severity`":`"info`",`"service`":`"demo`"}}"