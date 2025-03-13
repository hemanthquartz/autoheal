index=_internal sourcetype=splunkd
| search "splunkd daemon cannot be reached by splunkweb" OR "splunkd service: Failed" OR "splunkd crashed" OR "503 Service unavailable" OR "splunkd is down" OR "splunkd exited" OR "splunkd stopped"
| stats count by _time, host, source, sourcetype, log_level, message
| sort -_time