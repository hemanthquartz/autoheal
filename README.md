index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-7d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| bin _time span=1m
| stats 
    count(eval(httpStatus=500)) as count_500, 
    count(eval(httpStatus=502)) as count_502, 
    count(eval(httpStatus=503)) as count_503, 
    count(eval(httpStatus=504)) as count_504, 
    count(eval(httpStatus>=500)) as total_5xx_errors, 
    avg(serverResponseLatency) as avg_latency, 
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
| eval future_http_status = case(
    error_spike=1 OR latency_spike=1, "500",
    total_5xx_errors>0, "502",
    1=1, "none"
)
| fields _time, future_http_status, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, unique_clients
| fit GradientBoostingClassifier future_http_status from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients 
    into "Http5xxForecastModel" 
    options n_estimators=300 learning_rate=1.0 loss="exponential" class_weight="balanced"



| inputlookup pdeobservability_400500errors_1day.csv
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S%z")
| bin _time span=1m
| stats 
    count(eval(httpStatus=500)) AS count_500, 
    count(eval(httpStatus=502)) AS count_502, 
    count(eval(httpStatus=503)) AS count_503, 
    count(eval(httpStatus=504)) AS count_504, 
    count(eval(httpStatus>=500)) AS total_5xx_errors, 
    avg(serverResponseLatency) AS avg_latency, 
    dc(clientIP) AS unique_clients
    BY _time
| sort 0 _time
| streamstats window=5 avg(avg_latency) AS rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) AS rolling_error_rate
| delta avg_latency AS delta_latency
| delta rolling_error_rate AS delta_error
| eventstats stdev(avg_latency) AS stdev_latency, stdev(rolling_error_rate) AS stdev_error
| eval latency_spike = if(delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > stdev_error, 1, 0)
| eval severity_score = avg_latency + rolling_error_rate
| apply "Http5xxForecastModel"
| eval forecasted_http_status = predicted(future_http_status)
| eval probability = predicted_probability(forecasted_http_status)

| eval forecast_time = _time
| eval window_start = _time + 300
| eval window_end = _time + 900

| join type=left forecast_time [
    | inputlookup pdeobservability_400500errors_1day.csv
    | eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S%z")
    | where httpStatus>=500
    | bin _time span=1m
    | stats values(httpStatus) AS actual_http_status_list, count(eval(httpStatus>=500)) AS actual_count BY _time
    | rename _time AS verify_time
]
| eval actual_http_status = if(isnotnull(actual_http_status_list), mvindex(actual_http_status_list,0), "none")
| eval actual_count = coalesce(actual_count, 0)

| eval result_type = case(
    forecasted_http_status==actual_http_status AND forecasted_http_status!="none", "True Positive",
    forecasted_http_status=="none" AND actual_http_status=="none", "True Negative",
    forecasted_http_status!="none" AND actual_http_status=="none", "False Positive",
    forecasted_http_status=="none" AND actual_http_status!="none", "Missed Forecast",
    forecasted_http_status!=actual_http_status, "Wrong Code Predicted"
)

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = if(isnotnull(verify_time), strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST"), "")
| eval forecasted_count = if(forecasted_http_status!="none", 1, 0)

| table forecast_time_est, verify_time_est, forecasted_http_status, actual_http_status, result_type, forecasted_count, actual_count, probability, avg_latency, rolling_error_rate, severity_score, unique_clients
| sort forecast_time_est desc
