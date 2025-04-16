index=* sourcetype="mscs:azure:eventhub" source="*/network;" 
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval is_500=if(httpStatus >= 500, 1, 0)
| bin _time span=1m
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(body.properties.clientIp) as unique_clients
  by _time
| streamstats window=15 sum(error_count) as future_500_error_count
| eval future_500=if(future_500_error_count > 0, 1, 0)
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate
| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| table _time, future_500, avg_latency, total_sent, total_received, rolling_avg_latency, rolling_error_rate, unique_clients, hour, minute
| fit GradientBoostingClassifier future_500 from avg_latency total_sent total_received rolling_avg_latency rolling_error_rate unique_clients hour minute into 500ForecastModel




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval is_500=if(httpStatus >= 500, 1, 0)
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
| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| apply 500ForecastModel
| where 'predicted(future_500)'=1
| table _time, "predicted(future_500)", "probability(future_500)", avg_latency, rolling_error_rate, unique_clients
