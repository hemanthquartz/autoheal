Set-DnsClientServerAddress -InterfaceAlias "Ethernet 2" -ServerAddresses 168.63.129.16

Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -like "*Splunk Distribution of OpenTelemetry .NET*" } | ForEach-Object { $_.Uninstall() }

Get-WmiObject -Class Win32_Product |
  Where-Object { $_.Name -like "*Splunk Distribution of OpenTelemetry .NET*" } |
  ForEach-Object { $_.Uninstall() }

Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -like "*Splunk*" } | Select-Object Name

msiexec /i "C:\Users\provider_admin\AppData\Local\Temp\Splunk\OpenTelemetry Collector\splunk-otel-collector-*.msi" /qn

Invoke-WebRequest -Uri "https://dl.signalfx.com/splunk-otel-collector/releases/latest/splunk-otel-collector.msi" -OutFile "splunk-otel-collector.msi"
msiexec /i splunk-otel-collector.msi /qn