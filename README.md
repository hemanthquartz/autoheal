index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval is_500 = if(httpStatus >= 500, 1, 0)
| bin _time span=1m
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(body.properties.clientIp) as unique_clients
  by _time
| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| reverse
| streamstats window=10 sum(error_count) as future_500_error_count
| reverse

| eval severity_score = avg_latency * rolling_error_rate

| eval future_500 = if(
    severity_score >= 1.2
    OR (rolling_error_rate >= 2 AND avg_latency >= 0.5),
    1, 0
)

| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| fields _time, avg_latency, total_sent, total_received, rolling_avg_latency, rolling_error_rate, unique_clients, hour, minute, future_500, severity_score
| rename _time as forecast_time

| apply ForecastModel500

| eval verify_time = forecast_time + 600

| join type=left verify_time 
    [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval actual_500 = if(tonumber(httpStatus) >= 500, 1, 0)
    | bin verify_time span=1m
    | stats max(actual_500) as actual_500 by verify_time
    ]

| eval result_type = case(
    'predicted(future_500)'=1 AND actual_500=1, "True Positive",
    'predicted(future_500)'=1 AND actual_500=0, "False Positive",
    'predicted(future_500)'=0 AND actual_500=1, "Missed Forecast",
    'predicted(future_500)'=0 AND actual_500=0, "True Negative"
)

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %H:%M:%S %Z")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %H:%M:%S %Z")

| table forecast_time_est, verify_time_est, "predicted(future_500)", "probability(future_500)", actual_500, result_type, severity_score, avg_latency, rolling_error_rate, unique_clients
| sort forecast_time_est desc
| appendpipe [ stats count by result_type ]