index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| bin _time span=1m
| stats 
    avg(serverResponseLatency) as avg_latency,
    count(eval(httpStatus>=500)) as total_5xx_errors,
    dc(body.properties.clientIp) as unique_clients
  by _time
| sort 0 _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate
| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency, stdev(rolling_error_rate) as stdev_error
| eval latency_spike = if(delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > stdev_error, 1, 0)
| eval severity_score = avg_latency + rolling_error_rate

| apply Http5xxForecastModelBinary

| eval forecast_time = _time + 300   /* Forecast 5 minutes into future */
| join type=left forecast_time [
    inputlookup pdeobservability_400500errors_1day.csv
    | eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | where httpStatus>=500
    | bin _time span=1m
    | stats values(httpStatus) as actual_http_status_list, count(eval(httpStatus>=500)) as actual_count BY _time
    | rename _time as verify_time
]

| eval actual_http_status = if(isnotnull(actual_http_status_list), mvindex(actual_http_status_list, 0), "none")
| eval actual_count = coalesce(actual_count, 0)

| eval result_type = case(
    'predicted(future_error)'=1 AND actual_count>0, "True Positive",
    'predicted(future_error)'=0 AND actual_count=0, "True Negative",
    'predicted(future_error)'=1 AND actual_count=0, "False Positive",
    'predicted(future_error)'=0 AND actual_count>0, "Missed Forecast"
)

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, verify_time_est, 'predicted(future_error)', actual_http_status, result_type, actual_count, avg_latency, rolling_error_rate, severity_score, unique_clients
| sort forecast_time_est desc