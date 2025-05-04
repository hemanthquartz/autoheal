index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-60m latest=-5m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.clientPort output=clientPort
| spath path=body.properties.contentType output=contentType
| spath path=body.properties.error_info output=error_info
| spath path=body.properties.host output=host
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.httpVersion output=httpVersion
| spath path=body.properties.instanceId output=instanceId
| spath path=body.properties.originalHost output=originalHost
| spath path=body.properties.originalRequestUriWithArgs output=originalRequestUriWithArgs
| spath path=body.properties.requestUri output=requestUri
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.timeTaken output=timeTaken
| spath path=body.properties.userAgent output=userAgent
| spath path=body.properties.WAFEvaluationTime output=WAFEvaluationTime
| spath path=body.properties.WAFMode output=WAFMode
| eval clientPort=tonumber(clientPort),
        serverResponseLatency=tonumber(serverResponseLatency),
        timeTaken=tonumber(timeTaken),
        WAFEvaluationTime=tonumber(WAFEvaluationTime),
        httpStatus=tonumber(httpStatus)
| where isnotnull(clientIP) AND isnotnull(clientPort) AND isnotnull(contentType) AND isnotnull(error_info)
    AND isnotnull(host) AND isnotnull(httpMethod) AND isnotnull(httpVersion)
    AND isnotnull(instanceId) AND isnotnull(originalHost)
    AND isnotnull(originalRequestUriWithArgs) AND isnotnull(requestUri)
    AND isnotnull(serverResponseLatency) AND isnotnull(timeTaken)
    AND isnotnull(userAgent) AND isnotnull(WAFEvaluationTime)
    AND isnotnull(WAFMode)
| eval replication_factor=case(
    httpStatus=204,50,
    httpStatus=302,2,
    httpStatus=303,2,
    httpStatus=400,10,
    httpStatus=401,2,
    httpStatus=403,5,
    httpStatus=404,7,
    httpStatus=408,8,
    httpStatus=409,100,
    httpStatus=415,100,
    httpStatus=429,5,
    httpStatus=499,80,
    httpStatus=500,25,
    httpStatus=502,80,
    httpStatus=503,10,
    httpStatus=504,70,
    true(),1)
| eval repeat=mvjoin(mvrange(0, replication_factor), ",")
| makemv delim="," repeat
| mvexpand repeat
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
| eval error_5xx=if(httpStatus>=500 AND httpStatus<600,1,0)
| bin _time span=1m
| stats sum(error_5xx) as error_5xx_count avg(latency_ratio) as latency_ratio avg(waf_latency_ratio) as waf_latency_ratio avg(log_serverResponseLatency) as log_serverResponseLatency avg(log_timeTaken) as log_timeTaken avg(log_WAFEvaluationTime) as log_WAFEvaluationTime avg(latency_bucket) as latency_bucket avg(hour_of_day) as hour_of_day avg(weekday) as weekday by _time
| fit RandomForestClassifier error_5xx_count from latency_ratio waf_latency_ratio log_serverResponseLatency log_timeTaken log_WAFEvaluationTime latency_bucket hour_of_day weekday into realtime_5xx_forecaster







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