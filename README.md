index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-15m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.timeTaken output=timeTaken
| spath path=body.properties.WAFEvaluationTime output=WAFEvaluationTime
| eval serverResponseLatency=tonumber(serverResponseLatency),
        timeTaken=tonumber(timeTaken),
        WAFEvaluationTime=tonumber(WAFEvaluationTime),
        httpStatus=tonumber(httpStatus)
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
| bin _time span=1m
| stats avg(latency_ratio) as latency_ratio avg(waf_latency_ratio) as waf_latency_ratio avg(log_serverResponseLatency) as log_serverResponseLatency avg(log_timeTaken) as log_timeTaken avg(log_WAFEvaluationTime) as log_WAFEvaluationTime avg(latency_bucket) as latency_bucket avg(hour_of_day) as hour_of_day avg(weekday) as weekday sum(eval(httpStatus>=500 AND httpStatus<600)) as actual_5xx_count by _time
| apply realtime_5xx_forecaster as forecasted_5xx_count
| eval actual_time=_time, forecast_time=_time+600
| table actual_time forecast_time forecasted_5xx_count actual_5xx_count
| sort actual_time