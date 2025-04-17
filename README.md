| union max=2 
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m latest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus = 502
      | stats count as count
      | eval source = "RawLogCount"
    ]
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-25m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.properties.serverResponseLatency output=serverResponseLatency
      | spath path=body.properties.sentBytes output=sentBytes
      | spath path=body.properties.receivedBytes output=receivedBytes
      | spath path=body.timeStamp output=timeStamp
      | eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | bin _time span=1m
      | stats 
          avg(serverResponseLatency) as avg_latency,
          sum(sentBytes) as total_sent,
          sum(receivedBytes) as total_received,
          count(eval(httpStatus >= 500)) as error_count,
          dc(body.properties.clientIp) as unique_clients,
          values(httpStatus) as all_http_status
        by _time
      | streamstats window=5 avg(avg_latency) as rolling_avg_latency
      | streamstats window=5 avg(error_count) as rolling_error_rate
      | eval severity_score = avg_latency * rolling_error_rate
      | eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
      | rename _time as forecast_time
      | apply GBoostModel500
      | eval verify_time = forecast_time + 600
      | join type=left verify_time 
          [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-15m
            | spath path=body.properties.httpStatus output=httpStatus
            | spath path=body.timeStamp output=timeStamp
            | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
            | eval httpStatus = tonumber(httpStatus)
            | where httpStatus = 502
            | bin verify_time span=1m
            | stats values(httpStatus) as actual_http_status by verify_time
          ]
      | eval actual_http_status = mvindex(actual_http_status, 0)
      | where actual_http_status = 502
      | stats count as count
      | eval source = "ModelVerifiedCount"
    ]