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
    
| eval httpMethod_num=case(httpMethod=="GET",1,httpMethod=="POST",2,httpMethod=="PUT",3,httpMethod=="DELETE",4,true(),0)
| eval httpVersion_num=case(httpVersion=="HTTP/1.1",1,httpVersion=="HTTP/2",2,true(),0)
| eval wafMode_num=case(WAFMode=="Prevention",1,WAFMode=="Detection",2,true(),0)

| eval contentType_num=crc32(contentType),
        error_info_num=crc32(error_info),
        host_num=crc32(host),
        instanceId_num=crc32(instanceId),
        originalHost_num=crc32(originalHost),
        requestUri_num=crc32(requestUri),
        originalRequestUriWithArgs_num=crc32(originalRequestUriWithArgs),
        userAgent_num=crc32(userAgent),
        clientIP_num=crc32(clientIP)

| table _time httpStatus clientPort serverResponseLatency timeTaken WAFEvaluationTime httpMethod_num httpVersion_num wafMode_num contentType_num error_info_num host_num instanceId_num originalHost_num requestUri_num originalRequestUriWithArgs_num userAgent_num clientIP_num
