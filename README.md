index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.timeTaken output=timeTaken
| spath path=body.properties.WAFEvaluationTime output=WAFEvaluationTime
| eval serverResponseLatency=tonumber(serverResponseLatency),
        timeTaken=tonumber(timeTaken),
        WAFEvaluationTime=tonumber(WAFEvaluationTime),
        httpStatus=tonumber(httpStatus)
| bin _time span=1m
| eval hour_of_day=strftime(_time,"%H"),
        weekday=strftime(_time,"%w")
| eval latency_ratio=if(timeTaken>0, serverResponseLatency/timeTaken, 0),
        waf_latency_ratio=if(timeTaken>0, WAFEvaluationTime/timeTaken, 0)
| eval log_serverResponseLatency=log(serverResponseLatency+1),
        log_timeTaken=log(timeTaken+1),
        log_WAFEvaluationTime=log(WAFEvaluationTime+1)
| eval latency_bucket=case(
        serverResponseLatency<0.01,1,
        serverResponseLatency<0.1,2,
        serverResponseLatency<1,3,
        true(),4)
| stats count(eval(httpStatus>=500 AND httpStatus<600)) as actual_5xx_count
        avg(serverResponseLatency) as avg_serverResponseLatency
        avg(timeTaken) as avg_timeTaken
        avg(WAFEvaluationTime) as avg_WAFEvaluationTime
        avg(latency_ratio) as avg_latency_ratio
        avg(waf_latency_ratio) as avg_waf_latency_ratio
        avg(log_serverResponseLatency) as avg_log_serverResponseLatency
        avg(log_timeTaken) as avg_log_timeTaken
        avg(log_WAFEvaluationTime) as avg_log_WAFEvaluationTime
        avg(latency_bucket) as avg_latency_bucket
        avg(hour_of_day) as avg_hour_of_day
        avg(weekday) as avg_weekday
by _time
| sort _time
| streamstats current=f last(avg_serverResponseLatency) as last_avg_serverResponseLatency
               last(avg_timeTaken) as last_avg_timeTaken
               last(avg_WAFEvaluationTime) as last_avg_WAFEvaluationTime
               last(avg_latency_ratio) as last_avg_latency_ratio
               last(avg_waf_latency_ratio) as last_avg_waf_latency_ratio
               last(avg_log_serverResponseLatency) as last_avg_log_serverResponseLatency
               last(avg_log_timeTaken) as last_avg_log_timeTaken
               last(avg_log_WAFEvaluationTime) as last_avg_log_WAFEvaluationTime
               last(avg_latency_bucket) as last_avg_latency_bucket
               last(avg_hour_of_day) as last_avg_hour_of_day
               last(avg_weekday) as last_avg_weekday
| append [
    makeresults count=10
    | streamstats count as forecast_offset
    | eval _time=relative_time(now(), "+"+forecast_offset+"m")
    | eval avg_serverResponseLatency=last_avg_serverResponseLatency,
           avg_timeTaken=last_avg_timeTaken,
           avg_WAFEvaluationTime=last_avg_WAFEvaluationTime,
           avg_latency_ratio=last_avg_latency_ratio,
           avg_waf_latency_ratio=last_avg_waf_latency_ratio,
           avg_log_serverResponseLatency=last_avg_log_serverResponseLatency,
           avg_log_timeTaken=last_avg_log_timeTaken,
           avg_log_WAFEvaluationTime=last_avg_log_WAFEvaluationTime,
           avg_latency_bucket=last_avg_latency_bucket,
           avg_hour_of_day=strftime(_time,"%H"),
           avg_weekday=strftime(_time,"%w"),
           actual_5xx_count=null()
]
| fields - last_*
| sort - _time
| fillnull value=0 avg_serverResponseLatency avg_timeTaken avg_WAFEvaluationTime avg_latency_ratio avg_waf_latency_ratio avg_log_serverResponseLatency avg_log_timeTaken avg_log_WAFEvaluationTime avg_latency_bucket avg_hour_of_day avg_weekday
| apply error_5xx_forecaster into forecasted_5xx_count
| eval forecast_time_est=strftime(_time, "%Y-%m-%d %H:%M:%S %Z"),
        actual_time_est=if(isnull(actual_5xx_count), "Waiting for data", strftime(_time, "%Y-%m-%d %H:%M:%S %Z"))
| table forecast_time_est actual_time_est forecasted_5xx_count actual_5xx_count
| sort - forecast_time_est