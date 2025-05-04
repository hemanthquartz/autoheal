index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-120m latest=-10m
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
| eval label=if(httpStatus>=500 AND httpStatus<600,1,0)
| fields hour_of_day weekday latency_ratio waf_latency_ratio log_serverResponseLatency log_timeTaken log_WAFEvaluationTime latency_bucket label
| fit RandomForestClassifier label from hour_of_day weekday latency_ratio waf_latency_ratio log_serverResponseLatency log_timeTaken log_WAFEvaluationTime latency_bucket into future_500_forecaster






index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m latest=+15m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.timeTaken output=timeTaken
| spath path=body.properties.WAFEvaluationTime output=WAFEvaluationTime
| eval serverResponseLatency=tonumber(serverResponseLatency),
        timeTaken=tonumber(timeTaken),
        WAFEvaluationTime=tonumber(WAFEvaluationTime),
        httpStatus=tonumber(httpStatus)
| bin _time span=1m
| stats 
    avg(serverResponseLatency) as serverResponseLatency,
    avg(timeTaken) as timeTaken,
    avg(WAFEvaluationTime) as WAFEvaluationTime,
    count(eval(httpStatus>=500 AND httpStatus<600)) as actual_5xx_count
    by _time
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
| apply future_500_forecaster
| eval forecast_5xx_count=if(predicted_label=1,1,0)
| eval actual_time_est=strftime(_time,"%Y-%m-%d %H:%M:%S %Z"),
        forecast_time_est=strftime(relative_time(_time,"+10m"),"%Y-%m-%d %H:%M:%S %Z")
| table actual_time_est forecast_time_est forecast_5xx_count actual_5xx_count
