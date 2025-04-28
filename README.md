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
| eventstats values(clientPort) as values_clientPort, values(serverResponseLatency) as values_serverResponseLatency, values(timeTaken) as values_timeTaken, values(WAFEvaluationTime) as values_WAFEvaluationTime, values(clientIP_num) as values_clientIP_num, values(contentType_num) as values_contentType_num, values(error_info_num) as values_error_info_num, values(host_num) as values_host_num, values(httpMethod_num) as values_httpMethod_num, values(httpVersion_num) as values_httpVersion_num, values(instanceId_num) as values_instanceId_num, values(originalHost_num) as values_originalHost_num, values(originalRequestUriWithArgs_num) as values_originalRequestUriWithArgs_num, values(requestUri_num) as values_requestUri_num, values(userAgent_num) as values_userAgent_num, values(WAFMode_num) as values_WAFMode_num
| eval keep_clientPort=if(mvcount(values_clientPort)>1,1,0),
       keep_serverResponseLatency=if(mvcount(values_serverResponseLatency)>1,1,0),
       keep_timeTaken=if(mvcount(values_timeTaken)>1,1,0),
       keep_WAFEvaluationTime=if(mvcount(values_WAFEvaluationTime)>1,1,0),
       keep_clientIP_num=if(mvcount(values_clientIP_num)>1,1,0),
       keep_contentType_num=if(mvcount(values_contentType_num)>1,1,0),
       keep_error_info_num=if(mvcount(values_error_info_num)>1,1,0),
       keep_host_num=if(mvcount(values_host_num)>1,1,0),
       keep_httpMethod_num=if(mvcount(values_httpMethod_num)>1,1,0),
       keep_httpVersion_num=if(mvcount(values_httpVersion_num)>1,1,0),
       keep_instanceId_num=if(mvcount(values_instanceId_num)>1,1,0),
       keep_originalHost_num=if(mvcount(values_originalHost_num)>1,1,0),
       keep_originalRequestUriWithArgs_num=if(mvcount(values_originalRequestUriWithArgs_num)>1,1,0),
       keep_requestUri_num=if(mvcount(values_requestUri_num)>1,1,0),
       keep_userAgent_num=if(mvcount(values_userAgent_num)>1,1,0),
       keep_WAFMode_num=if(mvcount(values_WAFMode_num)>1,1,0)
| fields - values_*
| eval clientPort=if(keep_clientPort==1,clientPort,null()),
       serverResponseLatency=if(keep_serverResponseLatency==1,serverResponseLatency,null()),
       timeTaken=if(keep_timeTaken==1,timeTaken,null()),
       WAFEvaluationTime=if(keep_WAFEvaluationTime==1,WAFEvaluationTime,null()),
       clientIP_num=if(keep_clientIP_num==1,clientIP_num,null()),
       contentType_num=if(keep_contentType_num==1,contentType_num,null()),
       error_info_num=if(keep_error_info_num==1,error_info_num,null()),
       host_num=if(keep_host_num==1,host_num,null()),
       httpMethod_num=if(keep_httpMethod_num==1,httpMethod_num,null()),
       httpVersion_num=if(keep_httpVersion_num==1,httpVersion_num,null()),
       instanceId_num=if(keep_instanceId_num==1,instanceId_num,null()),
       originalHost_num=if(keep_originalHost_num==1,originalHost_num,null()),
       originalRequestUriWithArgs_num=if(keep_originalRequestUriWithArgs_num==1,originalRequestUriWithArgs_num,null()),
       requestUri_num=if(keep_requestUri_num==1,requestUri_num,null()),
       userAgent_num=if(keep_userAgent_num==1,userAgent_num,null()),
       WAFMode_num=if(keep_WAFMode_num==1,WAFMode_num,null())
| fields - keep_*
