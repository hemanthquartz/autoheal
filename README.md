index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m@m latest=-10m@m
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
    values(eval(if(httpStatus>=500,httpStatus,null()))) as forecasted_http_status
  by _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| eval severity_score = avg_latency * rolling_error_rate
| eval future_500 = if(rolling_error_rate > 2 AND severity_score > 0.8, 1, 0)
| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")

| eval is_high_latency = if(avg_latency > 0.35, 1, 0)
| eval is_high_severity = if(severity_score > 0.85, 1, 0)
| eval is_high_error_rate = if(rolling_error_rate > 2.5, 1, 0)

| fit GradientBoostingClassifier future_500 
    from avg_latency rolling_error_rate severity_score 
         is_high_latency is_high_severity is_high_error_rate 
    options loss="exponential" 
    into GBoostModel500_v3



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
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
    values(eval(if(httpStatus>=500,httpStatus,null()))) as all_http_status
  by _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| eval severity_score = avg_latency * rolling_error_rate

| eval is_high_latency = if(avg_latency > 0.35, 1, 0)
| eval is_high_severity = if(severity_score > 0.85, 1, 0)
| eval is_high_error_rate = if(rolling_error_rate > 2.5, 1, 0)

| rename _time as forecast_time
| apply GBoostModel500_v3

| eval verify_time = forecast_time + 600

| join type=left verify_time
    [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval httpStatus = tonumber(httpStatus)
    | where httpStatus >= 500
    | bin verify_time span=1m
    | stats values(httpStatus) as actual_http_status by verify_time
    ]

| eval forecasted_http_status = if('predicted(future_500)'=1, mvindex(all_http_status, 0), null())
| eval actual_http_status = mvindex(actual_http_status, 0)

| eval result_type = case(
    isnotnull(forecasted_http_status) AND isnotnull(actual_http_status) AND forecasted_http_status=actual_http_status,"True Positive",
    isnotnull(forecasted_http_status) AND isnull(actual_http_status),"False Positive",
    isnull(forecasted_http_status) AND isnotnull(actual_http_status),"Missed Forecast",
    isnotnull(forecasted_http_status) AND isnotnull(actual_http_status) AND forecasted_http_status != actual_http_status,"Wrong Code Predicted"
)

| where isnotnull(result_type)

| eval forecast_time_est = strftime(forecast_time-14400, "%Y-%m-%d %H:%M:%S EST")
| eval verify_time_est = strftime(verify_time-14400, "%Y-%m-%d %H:%M:%S EST")

| table forecast_time_est, verify_time_est, forecasted_http_status, actual_http_status, result_type, probability(future_500), avg_latency, rolling_error_rate, severity_score, unique_clients
| sort forecast_time_est desc
| appendpipe [ stats count by result_type ]