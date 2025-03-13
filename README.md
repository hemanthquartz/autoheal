index=_internal sourcetype=splunkd
| search "splunkd daemon cannot be reached by splunkweb" OR "splunkd service: Failed" OR "splunkd crashed" OR "503 Service unavailable" OR "splunkd is down" OR "splunkd exited" OR "splunkd stopped"
| stats count by _time, host, source, sourcetype, log_level, message
| sort -_time


(index=_internal OR index=_audit OR index=_introspection OR index=main OR index=your_custom_index)
sourcetype IN ("splunkd", "splunk_web_access", "splunk_web_service", "splunk_monitoring_console", "linux_syslog", "windows_eventlog")
| search "splunkd daemon cannot be reached" OR "splunkd service: Failed" OR "splunkd crashed" OR "503 Service unavailable" OR "splunkd exited" OR "splunkd stopped" OR "splunkweb failed to start" OR "KV Store is not available" OR "Indexing is paused due to storage issue" OR "heartbeat failure" OR "license violation" OR "out of memory" OR "low disk space"
| table _time host sourcetype message
| sort -_time