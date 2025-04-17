search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.clientIp output=clientIp
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| bin _time span=1m
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(clientIp) as unique_clients,
    values(httpStatus) as all_http_status
  by _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| rename _time as forecast_time
| apply GBoostModel500
| where 'probability(future_500)' > 0.6
| eval forecasted_http_status = if('predicted(future_500)'=1, mvfilter(all_http_status>=500), null())
| eval forecasted_http_status = mvindex(forecasted_http_status, 0)
| eval verify_time = forecast_time + 600

| join type=left verify_time 
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus >= 500
      | bin verify_time span=1m
      | stats values(httpStatus) as actual_http_status by verify_time
    ]

| eval actual_http_status = mvindex(actual_http_status, 0)
| eval result_type = case(
    isnull(forecasted_http_status) AND isnull(actual_http_status), null(),
    isnotnull(forecasted_http_status) AND forecasted_http_status=actual_http_status, "True Positive",
    isnotnull(forecasted_http_status) AND isnull(actual_http_status), "False Positive",
    isnull(forecasted_http_status) AND isnotnull(actual_http_status), "Missed Forecast",
    isnotnull(forecasted_http_status) AND isnotnull(actual_http_status) AND forecasted_http_status != actual_http_status, "Wrong Code Predicted"
)

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, verify_time_est, forecasted_http_status, actual_http_status, result_type, probability(future_500), avg_latency, rolling_error_rate, unique_clients
| sort forecast_time_est desc
| appendpipe [ stats count by result_type ]