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
| eventstats values(*) as values_*
| eval drop_fields=mvappend(
        if(mvcount(values_clientPort)==1,"clientPort",null()),
        if(mvcount(values_serverResponseLatency)==1,"serverResponseLatency",null()),
        if(mvcount(values_timeTaken)==1,"timeTaken",null()),
        if(mvcount(values_WAFEvaluationTime)==1,"WAFEvaluationTime",null()),
        if(mvcount(values_clientIP_num)==1,"clientIP_num",null()),
        if(mvcount(values_contentType_num)==1,"contentType_num",null()),
        if(mvcount(values_error_info_num)==1,"error_info_num",null()),
        if(mvcount(values_host_num)==1,"host_num",null()),
        if(mvcount(values_httpMethod_num)==1,"httpMethod_num",null()),
        if(mvcount(values_httpVersion_num)==1,"httpVersion_num",null()),
        if(mvcount(values_instanceId_num)==1,"instanceId_num",null()),
        if(mvcount(values_originalHost_num)==1,"originalHost_num",null()),
        if(mvcount(values_originalRequestUriWithArgs_num)==1,"originalRequestUriWithArgs_num",null()),
        if(mvcount(values_requestUri_num)==1,"requestUri_num",null()),
        if(mvcount(values_userAgent_num)==1,"userAgent_num",null()),
        if(mvcount(values_WAFMode_num)==1,"WAFMode_num",null())
    )
| fields - values_*
| foreach clientPort serverResponseLatency timeTaken WAFEvaluationTime clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num userAgent_num WAFMode_num
    [ eval <<FIELD>>=if(match(drop_fields,"<<FIELD>>"),null(),<<FIELD>>) ]
| fields - drop_fields
