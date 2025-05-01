index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-60m
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
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.timeStamp output=timeStamp
| eval _time=strptime(timeStamp,"%Y-%m-%dT%H:%M:%S")
| eval day_of_week=strftime(_time,"%A"),
        hour_of_day=strftime(_time,"%H"),
        minute=strftime(_time,"%M")
| where isnotnull(clientIP) AND isnotnull(clientPort) AND isnotnull(contentType) AND isnotnull(error_info)
    AND isnotnull(host) AND isnotnull(httpMethod) AND isnotnull(httpVersion)
    AND isnotnull(instanceId) AND isnotnull(originalHost)
    AND isnotnull(originalRequestUriWithArgs) AND isnotnull(requestUri)
    AND isnotnull(serverResponseLatency) AND isnotnull(timeTaken)
    AND isnotnull(userAgent) AND isnotnull(WAFEvaluationTime)
    AND isnotnull(WAFMode) AND isnotnull(httpStatus)
| eval clientIP_num=tonumber(substr(md5(clientIP),1,7),16),
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
        WAFMode_num=tonumber(substr(md5(WAFMode),1,7),16),
        day_num=tonumber(strftime(_time,"%w")),
        hour_num=tonumber(hour_of_day),
        minute_num=tonumber(minute),
        responseTimeBucket=case(timeTaken<200,"fast", timeTaken>=200 AND timeTaken<1000,"moderate", timeTaken>=1000,"slow"),
        latencyBucket=case(serverResponseLatency<200,"low", serverResponseLatency>=200 AND serverResponseLatency<800,"medium", serverResponseLatency>=800,"high"),
        statusType=case(httpStatus>=500,"5xx", httpStatus>=400,"4xx", httpStatus>=300,"3xx", httpStatus>=200,"2xx", true(),"other")
| eval responseTimeBucket_num=tonumber(substr(md5(responseTimeBucket),1,7),16),
        latencyBucket_num=tonumber(substr(md5(latencyBucket),1,7),16)
| table _time httpStatus statusType clientPort serverResponseLatency timeTaken WAFEvaluationTime 
        clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num 
        instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num 
        userAgent_num WAFMode_num day_num hour_num minute_num 
        responseTimeBucket_num latencyBucket_num