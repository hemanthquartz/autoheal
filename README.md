index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
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
    count as total_http_status,
    count(eval(httpStatus>=500)) as total_5xx_errors,
    count(eval(httpStatus=502)) as count_502,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(abs(delta_latency) > stdev_latency, 1, 0)
| eval error_spike = if(abs(delta_error) > stdev_error, 1, 0)
| eval severity_score = (avg_latency + rolling_error_rate + latency_spike + error_spike) * unique_clients

| apply FinalModel_502
| rename "predicted(future_count_502)" as predicted_count_502

| eval forecast_time = _time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")
| eval verify_time = _time + 300   // predict for 5 minutes ahead
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p %Z")

| join type=left verify_time
    [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval httpStatus = tonumber(httpStatus)
    | where httpStatus = 502
    | bin verify_time span=1m
    | stats 
        count as count_502_actual
      by verify_time
    ]

| eval result_type = case(
    isnull(count_502_actual), null(),
    isnotnull(count_502_actual) AND predicted_count_502 > 0, "True Positive",
    isnotnull(count_502_actual) AND predicted_count_502 = 0, "Missed Forecast",
    isnull(count_502_actual) AND predicted_count_502 > 0, "False Positive",
    isnull(count_502_actual) AND predicted_count_502 = 0, "True Negative"
)

| eval total_forecast_502 = round(predicted_count_502,0)
| eval total_actual_502 = count_502_actual

| table forecast_time_est, verify_time_est, total_forecast_502, total_actual_502, result_type, 
        avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, total_5xx_errors, total_http_status, unique_clients

| sort forecast_time_est desc