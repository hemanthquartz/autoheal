index=<your_index> sourcetype IN ("kube:container:controller", "kube:container:konnectivity-agent", "kube:container:gatekeeper-audit-container", "kube:container:azure-policy", "kube:container:cns-container", "msscs:azure:eventhub")
| rex field=_raw "(?i)(error|fail|exception|timeout|unreachable|down|crash|denied|oom|terminated|unhealthy|container.*stopped|unauthorized|policy violation)" AS issue_detected
| where isnotnull(issue_detected)
| stats count by sourcetype issue_detected
| sort -count