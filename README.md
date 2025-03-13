index=* 
| foreach * 
  [ eval temp_match=if(match(<<FIELD>>, "(?i)(error|fail|crash|timeout|oom|out of memory|resource|exception|terminate|kill|warn|alert|fail|dead|abort)"), 1, 0) 
    | eval <<FIELD>>_issue=if(temp_match=1, <<FIELD>>, null()) ]
| where temp_match=1
| eval issue_field=mvappend('log_message_issue', 'message_issue', 'status_issue', 'container_status_issue', 'event_issue', 'error_issue')
| mvexpand issue_field
| eval severity = case(
    match(issue_field, "(?i)crash|kill|terminate|dead|abort"), "Critical",
    match(issue_field, "(?i)error|exception|fail"), "High",
    match(issue_field, "(?i)warn|alert|timeout"), "Medium",
    true(), "Low"
  )
| table _time, sourcetype, host, issue_field, severity
| sort -_time
| fields - _raw, temp_match