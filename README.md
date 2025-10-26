$AFD_HOST = "splunkalerts-cedkgdhyhygrdyds.a03.azurefd.net"

curl.exe -i -X POST "https://$AFD_HOST/splunk/dispatch" `
  -H "Content-Type: application/json" `
  --data "{`"event_type`":`"splunk_alert`",`"client_payload`":{`"severity`":`"info`",`"service`":`"demo`"}}"


FrontDoorAccessLog
| where Resource == "<your-frontdoor-profile-name>"
| where requestUri_s contains "/splunk/dispatch"
| project TimeGenerated, clientIp_s, httpMethod_s, requestUri_s, routingRuleName_s,
          backendHostname_s, backendPort_d, backendStatusCode_d, responseStatusCode_d,
          originPath_s, originGroupName_s, originName_s
| sort by TimeGenerated desc