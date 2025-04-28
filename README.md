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
        WAFMode_num=tonumber(substr(md5(WAFMode),1,7),16)
| fields _time httpStatus clientPort serverResponseLatency timeTaken WAFEvaluationTime clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num userAgent_num WAFMode_num
| eventstats dc(clientPort) as dc_clientPort,
             dc(serverResponseLatency) as dc_serverResponseLatency,
             dc(timeTaken) as dc_timeTaken,
             dc(WAFEvaluationTime) as dc_WAFEvaluationTime,
             dc(clientIP_num) as dc_clientIP_num,
             dc(contentType_num) as dc_contentType_num,
             dc(error_info_num) as dc_error_info_num,
             dc(host_num) as dc_host_num,
             dc(httpMethod_num) as dc_httpMethod_num,
             dc(httpVersion_num) as dc_httpVersion_num,
             dc(instanceId_num) as dc_instanceId_num,
             dc(originalHost_num) as dc_originalHost_num,
             dc(originalRequestUriWithArgs_num) as dc_originalRequestUriWithArgs_num,
             dc(requestUri_num) as dc_requestUri_num,
             dc(userAgent_num) as dc_userAgent_num,
             dc(WAFMode_num) as dc_WAFMode_num
| eval clientPort=if(dc_clientPort>1, clientPort, null()),
        serverResponseLatency=if(dc_serverResponseLatency>1, serverResponseLatency, null()),
        timeTaken=if(dc_timeTaken>1, timeTaken, null()),
        WAFEvaluationTime=if(dc_WAFEvaluationTime>1, WAFEvaluationTime, null()),
        clientIP_num=if(dc_clientIP_num>1, clientIP_num, null()),
        contentType_num=if(dc_contentType_num>1, contentType_num, null()),
        error_info_num=if(dc_error_info_num>1, error_info_num, null()),
        host_num=if(dc_host_num>1, host_num, null()),
        httpMethod_num=if(dc_httpMethod_num>1, httpMethod_num, null()),
        httpVersion_num=if(dc_httpVersion_num>1, httpVersion_num, null()),
        instanceId_num=if(dc_instanceId_num>1, instanceId_num, null()),
        originalHost_num=if(dc_originalHost_num>1, originalHost_num, null()),
        originalRequestUriWithArgs_num=if(dc_originalRequestUriWithArgs_num>1, originalRequestUriWithArgs_num, null()),
        requestUri_num=if(dc_requestUri_num>1, requestUri_num, null()),
        userAgent_num=if(dc_userAgent_num>1, userAgent_num, null()),
        WAFMode_num=if(dc_WAFMode_num>1, WAFMode_num, null())
| fields - dc_*
| fields _time httpStatus clientPort serverResponseLatency timeTaken WAFEvaluationTime clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num userAgent_num WAFMode_num
