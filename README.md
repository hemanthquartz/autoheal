index=* 
| foreach * 
  [ eval temp_match=if(match(<<FIELD>>, "(?i)(error|fail|crash|timeout|out of memory|resource limit|exception|terminated|killed|warning|alert|failed)"), 1, 0) 
    | eval <<FIELD>>_issue=if(temp_match=1, <<FIELD>>, null()) ]
| where temp_match=1 OR container_status="Failed" OR status="Failed" OR exit_code>0 OR error_code>0
| eval severity = case(
    match('log_message_issue', "crash|killed|terminated") OR match('status_issue', "Failed"), "Critical",
    match('log_message_issue', "error|exception") OR match('error_code_issue', "[1-9]"), "High",
    match('log_message_issue', "warning|timeout|alert"), "Medium",
    true(), "Low"
  )
| table _time, sourcetype, host, log_message_issue, status_issue, container_status, exit_code, error_code, severity
| sort -_time
| fields - _raw, temp_match