index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-60m
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
    httpStatus=409,100,
    httpStatus=415,100,
    httpStatus=499,100,
    httpStatus=502,100,
    httpStatus=504,80,
    httpStatus=500,20,
    httpStatus=503,8,
    httpStatus=400,8,
    httpStatus=404,6,
    httpStatus=403,4,
    httpStatus=408,8,
    httpStatus=429,4,
    httpStatus=204,50,
    httpStatus=302,2,
    httpStatus=303,2,
    true(),1)
| eval repeat=mvjoin(mvrange(0, replication_factor), ",")
| makemv delim="," repeat
| mvexpand repeat
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
        serverResponseLatency_num=serverResponseLatency,
        timeTaken_num=timeTaken,
        userAgent_num=tonumber(substr(md5(userAgent),1,7),16),
        WAFEvaluationTime_num=WAFEvaluationTime,
        WAFMode_num=tonumber(substr(md5(WAFMode),1,7),16)
| table _time httpStatus clientIP_num clientPort_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num serverResponseLatency_num timeTaken_num userAgent_num WAFEvaluationTime_num WAFMode_num