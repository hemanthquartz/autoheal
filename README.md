index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-15m latest=now
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
| eval clientPort=coalesce(tonumber(clientPort),0),
        serverResponseLatency=coalesce(tonumber(serverResponseLatency),0),
        timeTaken=coalesce(tonumber(timeTaken),0),
        WAFEvaluationTime=coalesce(tonumber(WAFEvaluationTime),0),
        httpStatus=coalesce(tonumber(httpStatus),0)
| fillnull value=""
| eval clientIP=coalesce(clientIP,"none"),
        contentType=coalesce(contentType,"none"),
        error_info=coalesce(error_info,"none"),
        host=coalesce(host,"none"),
        httpMethod=coalesce(httpMethod,"none"),
        httpVersion=coalesce(httpVersion,"none"),
        instanceId=coalesce(instanceId,"none"),
        originalHost=coalesce(originalHost,"none"),
        originalRequestUriWithArgs=coalesce(originalRequestUriWithArgs,"none"),
        requestUri=coalesce(requestUri,"none"),
        userAgent=coalesce(userAgent,"none"),
        WAFMode=coalesce(WAFMode,"none")
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
| apply httpStatus502_forecast_model as prediction
| bin _time span=1m
| eval forecast_time=_time+600
| stats sum(prediction) as forecasted_502_count, sum(eval(httpStatus=502)) as actual_502_count by _time, forecast_time
| eval forecast_time_est=strftime(forecast_time, "%Y-%m-%d %H:%M:%S %Z"), actual_time_est=strftime(_time, "%Y-%m-%d %H:%M:%S %Z")
| table forecast_time_est actual_time_est forecasted_502_count actual_502_count
| sort - forecast_time_est