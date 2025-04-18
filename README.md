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
| eval future_error = if(error_spike==1 OR latency_spike==1 OR total_5xx_errors>0, 1, 0)

| fields _time, future_error, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, unique_clients
| fit GradientBoostingClassifier future_error 
    from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients 
    into "Http5xxForecastModelBinary" 
    options n_estimators=300 learning_rate=1.0 loss="exponential" class_weight="balanced"