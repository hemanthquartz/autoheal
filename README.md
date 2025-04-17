index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=30s
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(body.properties.clientIp) as unique_clients,
    values(eval(if(httpStatus>=500,httpStatus,null()))) as all_http_status
  by _time
| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(delta_latency > 0.1 AND delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > 0.2 AND delta_error > stdev_error, 1, 0)

| eval severity_score = avg_latency * rolling_error_rate

| apply GBoostModel500Sensitive

| rename _time as forecast_time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")
| eval verify_time = forecast_time + 600

| join type=left verify_time
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus >= 500
      | bin verify_time span=30s
      | stats values(httpStatus) as actual_http_status by verify_time
    ]

| eval forecasted_http_status = if('predicted(future_500)'=1, mvindex(all_http_status,0), null())
| eval actual_http_status = mvindex(actual_http_status,0)

| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p %Z")

| eval result_type = case(
    isnotnull(forecasted_http_status) AND isnotnull(actual_http_status) AND forecasted_http_status=actual_http_status, "True Positive",
    isnotnull(forecasted_http_status) AND isnull(actual_http_status), "False Positive",
    isnull(forecasted_http_status) AND isnotnull(actual_http_status), "Missed Forecast",
    isnotnull(forecasted_http_status) AND isnotnull(actual_http_status) AND forecasted_http_status != actual_http_status, "Wrong Code Predicted",
    true(), "True Negative"
)

| table forecast_time_est, verify_time_est, forecasted_http_status, actual_http_status, result_type, probability(future_500), avg_latency, rolling_error_rate, severity_score, unique_clients
| sort forecast_time_est desc