(index=_internal OR index=_audit OR index=_introspection OR index=main OR index=your_custom_index)
sourcetype IN ("splunkd", "splunk_web_access", "splunk_web_service", "splunk_monitoring_console", "linux_syslog", "windows_eventlog")
| search "ERROR" OR "WARN" OR "FATAL"
| rex field=_raw "(?i)error\s*(code)?[:=]?\s*(?P<error_code>\d{3,5})"
| stats count by error_code sourcetype
| sort -count