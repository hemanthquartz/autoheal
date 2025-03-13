index=<your_index> sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub")
| rex field=_raw "(?i)(error|fail|exception|timeout|unreachable|down|crash|denied|oom|terminated|unhealthy|container.*stopped|unauthorized|policy violation)" AS issue_detected
| where isnotnull(issue_detected)
| stats count by sourcetype issue_detected
| sort -count

index=xdl_pde_devops_observability_prod sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub")
| rex field=_raw "(?i)(?<issue_detected>error|fail|exception|timeout|unreachable|down|crash|denied|oom|terminated|unhealthy|container.*stopped|unauthorized|policy violation)"
| where isnotnull(issue_detected)
| stats count by sourcetype issue_detected
| sort -count

index=xdl_pde_devops_observability_prod sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub")
| search "*error*" OR "*fail*" OR "*exception*" OR "*timeout*" OR "*unreachable*" OR "*down*" OR "*crash*" OR "*denied*" OR "*oom*" OR "*terminated*" OR "*unhealthy*" OR "*stopped*" OR "*unauthorized*" OR "*policy violation*"
| stats count by sourcetype
| sort -count

index=xdl_pde_devops_observability_prod sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub")
| search "*error*" OR "*fail*" OR "*exception*" OR "*timeout*" OR "*unreachable*" OR "*down*" OR "*crash*" OR "*denied*" OR "*oom*" OR "*terminated*" OR "*unhealthy*" OR "*stopped*" OR "*unauthorized*" OR "*policy violation*"
| eval issue_detected = 
    case(
        match(_raw, "(?i)error"), "Error",
        match(_raw, "(?i)fail"), "Failure",
        match(_raw, "(?i)exception"), "Exception",
        match(_raw, "(?i)timeout"), "Timeout",
        match(_raw, "(?i)unreachable"), "Unreachable",
        match(_raw, "(?i)down"), "Down",
        match(_raw, "(?i)crash"), "Crash",
        match(_raw, "(?i)denied"), "Denied",
        match(_raw, "(?i)oom"), "OutOfMemory",
        match(_raw, "(?i)terminated"), "Terminated",
        match(_raw, "(?i)unhealthy"), "Unhealthy",
        match(_raw, "(?i)stopped"), "Stopped",
        match(_raw, "(?i)unauthorized"), "Unauthorized",
        match(_raw, "(?i)policy violation"), "Policy Violation"
    )
| stats count by issue_detected sourcetype
| sort -count


