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
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
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

| apply FinalModel_500
| rename "predicted(future_count_500)" as predicted_count_500

| apply FinalModel_502
| rename "predicted(future_count_502)" as predicted_count_502

| apply FinalModel_503
| rename "predicted(future_count_503)" as predicted_count_503

| apply FinalModel_504
| rename "predicted(future_count_504)" as predicted_count_504

| eval forecast_time = _time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")
| eval verify_time = _time + 300  // verifying after 5 minutes
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p %Z")

| join type=left verify_time
    [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval httpStatus = tonumber(httpStatus)
    | where httpStatus >= 500
    | bin verify_time span=1m
    | stats 
        values(httpStatus) as actual_http_status,
        count(eval(httpStatus=500)) as count_500_actual,
        count(eval(httpStatus=502)) as count_502_actual,
        count(eval(httpStatus=503)) as count_503_actual,
        count(eval(httpStatus=504)) as count_504_actual
      by verify_time
    ]

| eval result_type = case(
    isnull(actual_http_status), null(),
    isnotnull(actual_http_status) AND (predicted_count_500 + predicted_count_502 + predicted_count_503 + predicted_count_504) > 0, "True Positive",
    isnotnull(actual_http_status) AND (predicted_count_500 + predicted_count_502 + predicted_count_503 + predicted_count_504) = 0, "Missed Forecast",
    isnull(actual_http_status) AND (predicted_count_500 + predicted_count_502 + predicted_count_503 + predicted_count_504) > 0, "False Positive",
    isnull(actual_http_status) AND (predicted_count_500 + predicted_count_502 + predicted_count_503 + predicted_count_504) = 0, "True Negative"
)

| eval total_actual_5xx = count_500_actual + count_502_actual + count_503_actual + count_504_actual
| eval total_forecast_5xx = round(predicted_count_500,0) + round(predicted_count_502,0) + round(predicted_count_503,0) + round(predicted_count_504,0)

| table forecast_time_est, verify_time_est,
    predicted_count_500, predicted_count_502, predicted_count_503, predicted_count_504, total_forecast_5xx,
    count_500_actual, count_502_actual, count_503_actual, count_504_actual, total_actual_5xx,
    result_type,
    avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, total_5xx_errors, total_http_status, unique_clients

| sort forecast_time_est desc