index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-7d
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
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| streamstats window=10 sum(error_count) as future_500_error_count offset=-10
| eval future_500 = if(future_500_error_count > 0, 1, 0)
| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| fields _time, future_500, avg_latency, total_sent, total_received, rolling_avg_latency, rolling_error_rate, unique_clients, hour, minute
| fit GradientBoostingClassifier future_500 from avg_latency total_sent total_received rolling_avg_latency rolling_error_rate unique_clients hour minute into ForecastModel500 options loss="log_loss"



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
    dc(body.properties.clientIp) as unique_clients,
    max(_time) as feature_time
  by _time

| sort 0 _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate

| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| fields feature_time, avg_latency, total_sent, total_received, rolling_avg_latency, rolling_error_rate, unique_clients, hour, minute
| apply ForecastModel500
| rename feature_time as forecast_time

| eval verify_time = forecast_time + 600

| join type=left verify_time 
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval actual_500 = if(tonumber(httpStatus) >= 500, 1, 0)
    | bin verify_time span=1m
    | stats max(actual_500) as actual_500 by verify_time
    ]

| table forecast_time, "predicted(future_500)", "probability(future_500)", actual_500, avg_latency, rolling_error_rate, unique_clients
| sort forecast_time desc
