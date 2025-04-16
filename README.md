| makemv delim="|" thresholds="2,3,4|1.5,2,2.5|0.3,0.4,0.5"
| mvexpand thresholds
| eval split=split(thresholds, ",")
| eval f_count=mvindex(split, 0), err_rate=mvindex(split, 1), latency=mvindex(split, 2)
| map search="
    search index=* sourcetype=mscs:azure:eventhub source=*network* earliest=-20m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.properties.serverResponseLatency output=serverResponseLatency
    | spath path=body.properties.sentBytes output=sentBytes
    | spath path=body.properties.receivedBytes output=receivedBytes
    | spath path=body.timeStamp output=timeStamp
    | eval _time = strptime(timeStamp, \"%Y-%m-%dT%H:%M:%S\")
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
    | eval future_500 = if(future_500_error_count >= '.f_count.' AND rolling_error_rate >= '.err_rate.' AND avg_latency >= '.latency.', 1, 0)
    | rename _time as forecast_time
    | eval verify_time = forecast_time + 600
    | join type=left verify_time 
        [
        search index=* sourcetype=mscs:azure:eventhub source=*network* earliest=-10m
        | spath path=body.properties.httpStatus output=httpStatus
        | spath path=body.timeStamp output=timeStamp
        | eval verify_time = strptime(timeStamp, \"%Y-%m-%dT%H:%M:%S\")
        | eval actual_500 = if(tonumber(httpStatus) >= 500, 1, 0)
        | bin verify_time span=1m
        | stats max(actual_500) as actual_500 by verify_time
        ]
    | eval result_type = case(
        future_500=1 AND actual_500=1, \"True Positive\",
        future_500=1 AND actual_500=0, \"False Positive\",
        future_500=0 AND actual_500=1, \"Missed Forecast\",
        future_500=0 AND actual_500=0, \"True Negative\"
    )
    | stats count by result_type
    | eval f_count=\"'.f_count.'\", err_rate=\"'.err_rate.'\", latency=\"'.latency.'\"
"