index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-120m latest=-15m
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
| eval clientIP_num=tonumber(substr(md5(clientIP),1,7),16),
        clientPort_num=clientPort,
        contentType_num=tonumber(substr(md5(contentType),1,7),16),
        error_info_num=tonumber(substr(md5(error_info),1,7),16),
        host_num=tonumber(substr(md5(host),1,7),16),
        httpMethod_num=tonumber(substr(md5(httpMethod),1,7),16),
        httpVersion_num=tonumber(substr(md5(httpVersion),1,7),16),
        instanceId_num=tonumber(substr(md5(instanceId),1,7),16),
        originalHost_num=tonumber(substr(md5(originalHost),1,7),16),
        originalRequestUriWithArgs_num=tonumber(substr(md5(originalRequestUriWithArgs),1,7),16),
        requestUri_num=tonumber(substr(md5(requestUri),1,7),16),
        userAgent_num=tonumber(substr(md5(userAgent),1,7),16),
        WAFMode_num=tonumber(substr(md5(WAFMode),1,7),16)
| eval serverResponseLatency_num=serverResponseLatency,
        timeTaken_num=timeTaken,
        WAFEvaluationTime_num=WAFEvaluationTime
| bin _time span=1m
| stats count(eval(httpStatus>=500 AND httpStatus<600)) as error_5xx_count
        avg(serverResponseLatency_num) as avg_serverResponseLatency
        avg(timeTaken_num) as avg_timeTaken
        avg(WAFEvaluationTime_num) as avg_WAFEvaluationTime
        avg(latency_ratio) as avg_latency_ratio
        avg(waf_latency_ratio) as avg_waf_latency_ratio
        avg(log_serverResponseLatency) as avg_log_serverResponseLatency
        avg(log_timeTaken) as avg_log_timeTaken
        avg(log_WAFEvaluationTime) as avg_log_WAFEvaluationTime
        avg(latency_bucket) as avg_latency_bucket
        avg(hour_of_day) as avg_hour_of_day
        avg(weekday) as avg_weekday
by _time
| fillnull value=0
| fit RandomForestRegressor error_5xx_count from avg_serverResponseLatency avg_timeTaken avg_WAFEvaluationTime avg_latency_ratio avg_waf_latency_ratio avg_log_serverResponseLatency avg_log_timeTaken avg_log_WAFEvaluationTime avg_latency_bucket avg_hour_of_day avg_weekday into error_5xx_forecaster





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
| appendpipe [
    makeresults
    | eval _time=relative_time(now(), "+1m")
    | append [| makeresults | eval _time=relative_time(now(), "+2m")]
    | append [| makeresults | eval _time=relative_time(now(), "+3m")]
    | append [| makeresults | eval _time=relative_time(now(), "+4m")]
    | append [| makeresults | eval _time=relative_time(now(), "+5m")]
    | append [| makeresults | eval _time=relative_time(now(), "+6m")]
    | append [| makeresults | eval _time=relative_time(now(), "+7m")]
    | append [| makeresults | eval _time=relative_time(now(), "+8m")]
    | append [| makeresults | eval _time=relative_time(now(), "+9m")]
    | append [| makeresults | eval _time=relative_time(now(), "+10m")]
]
| sort _time
| apply error_5xx_forecaster into forecasted_5xx_count
| eval forecast_time_est=strftime(_time, "%Y-%m-%d %H:%M:%S %Z"),
        actual_time_est=if(isnull(actual_5xx_count), "Waiting for data", strftime(_time, "%Y-%m-%d %H:%M:%S %Z"))
| table actual_time_est forecast_time_est forecasted_5xx_count actual_5xx_count