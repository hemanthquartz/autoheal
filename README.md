$AFD_HOST = "splunkalerts-cedkgdhyhygrdyds.a03.azurefd.net"

curl.exe -i -X POST "https://$AFD_HOST/splunk/dispatch" `
  -H "Content-Type: application/json" `
  --data "{`"event_type`":`"splunk_alert`",`"client_payload`":{`"severity`":`"info`",`"service`":`"demo`"}}"