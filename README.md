Set-DnsClientServerAddress -InterfaceAlias "Ethernet 2" -ServerAddresses 168.63.129.16

Get-WmiObject -Class Win32_Product | Where-Object { $_.Name -like "*Splunk Distribution of OpenTelemetry .NET*" } | ForEach-Object { $_.Uninstall() }