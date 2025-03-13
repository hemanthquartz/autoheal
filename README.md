index=_internal OR index=_audit OR index=_introspection OR index=xdl_pde_devops_observability_prod
sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub", "splunkd", "splunk_web_access", "splunk_web_service")
| search "*splunkd exited*" OR "*splunkd stopped*" OR "*Connection reset by peer*" OR "*systemd: splunkd.service: Failed*" OR "*Out of memory*" OR "*disk space low*" OR "*TCP connection refused*" OR "*indexing latency exceeded*" OR "*search peer down*" OR "*heartbeat failure*" OR "*license violation*" OR "*bundle replication failure*" OR "*crash*" OR "*terminated*" OR "*unreachable*" OR "*splunkweb failed to start*" OR "*KV Store is not available*" OR "*Indexing is paused due to storage issue*"
| eval issue_detected = 
    case(
        match(_raw, "(?i)splunkd exited"), "SplunkD Process Exited",
        match(_raw, "(?i)splunkd stopped"), "SplunkD Process Stopped",
        match(_raw, "(?i)connection reset by peer"), "Connection Reset",
        match(_raw, "(?i)systemd: splunkd.service: Failed"), "Splunk Service Failed",
        match(_raw, "(?i)out of memory"), "Out of Memory",
        match(_raw, "(?i)disk space low"), "Low Disk Space",
        match(_raw, "(?i)tcp connection refused"), "TCP Connection Refused",
        match(_raw, "(?i)indexing latency exceeded"), "Indexing Latency High",
        match(_raw, "(?i)search peer down"), "Search Peer Down",
        match(_raw, "(?i)heartbeat failure"), "Cluster Heartbeat Failure",
        match(_raw, "(?i)license violation"), "License Violation",
        match(_raw, "(?i)bundle replication failure"), "Bundle Replication Failure",
        match(_raw, "(?i)crash"), "Crash Detected",
        match(_raw, "(?i)terminated"), "Splunk Process Terminated",
        match(_raw, "(?i)unreachable"), "Splunk Unreachable",
        match(_raw, "(?i)splunkweb failed to start"), "SplunkWeb Startup Failure",
        match(_raw, "(?i)kv store is not available"), "KV Store Down",
        match(_raw, "(?i)indexing is paused due to storage issue"), "Indexing Paused - Storage Issue"
    )
| stats count by issue_detected sourcetype
| sort -count