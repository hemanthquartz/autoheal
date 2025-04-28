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
| table _time httpStatus clientPort serverResponseLatency timeTaken WAFEvaluationTime clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num userAgent_num WAFMode_num
| eventstats values(clientPort) as clientPort_values, values(serverResponseLatency) as serverResponseLatency_values, values(timeTaken) as timeTaken_values, values(WAFEvaluationTime) as WAFEvaluationTime_values, values(clientIP_num) as clientIP_num_values, values(contentType_num) as contentType_num_values, values(error_info_num) as error_info_num_values, values(host_num) as host_num_values, values(httpMethod_num) as httpMethod_num_values, values(httpVersion_num) as httpVersion_num_values, values(instanceId_num) as instanceId_num_values, values(originalHost_num) as originalHost_num_values, values(originalRequestUriWithArgs_num) as originalRequestUriWithArgs_num_values, values(requestUri_num) as requestUri_num_values, values(userAgent_num) as userAgent_num_values, values(WAFMode_num) as WAFMode_num_values
| eval clientPort_keep=if(mvcount(clientPort_values)>1,1,0),
        serverResponseLatency_keep=if(mvcount(serverResponseLatency_values)>1,1,0),
        timeTaken_keep=if(mvcount(timeTaken_values)>1,1,0),
        WAFEvaluationTime_keep=if(mvcount(WAFEvaluationTime_values)>1,1,0),
        clientIP_num_keep=if(mvcount(clientIP_num_values)>1,1,0),
        contentType_num_keep=if(mvcount(contentType_num_values)>1,1,0),
        error_info_num_keep=if(mvcount(error_info_num_values)>1,1,0),
        host_num_keep=if(mvcount(host_num_values)>1,1,0),
        httpMethod_num_keep=if(mvcount(httpMethod_num_values)>1,1,0),
        httpVersion_num_keep=if(mvcount(httpVersion_num_values)>1,1,0),
        instanceId_num_keep=if(mvcount(instanceId_num_values)>1,1,0),
        originalHost_num_keep=if(mvcount(originalHost_num_values)>1,1,0),
        originalRequestUriWithArgs_num_keep=if(mvcount(originalRequestUriWithArgs_num_values)>1,1,0),
        requestUri_num_keep=if(mvcount(requestUri_num_values)>1,1,0),
        userAgent_num_keep=if(mvcount(userAgent_num_values)>1,1,0),
        WAFMode_num_keep=if(mvcount(WAFMode_num_values)>1,1,0)
| fields - *_values
| fields _time httpStatus 
    clientPort serverResponseLatency timeTaken WAFEvaluationTime clientIP_num contentType_num error_info_num host_num httpMethod_num httpVersion_num instanceId_num originalHost_num originalRequestUriWithArgs_num requestUri_num userAgent_num WAFMode_num
| eval clientPort=if(clientPort_keep=1,clientPort,null()),
        serverResponseLatency=if(serverResponseLatency_keep=1,serverResponseLatency,null()),
        timeTaken=if(timeTaken_keep=1,timeTaken,null()),
        WAFEvaluationTime=if(WAFEvaluationTime_keep=1,WAFEvaluationTime,null()),
        clientIP_num=if(clientIP_num_keep=1,clientIP_num,null()),
        contentType_num=if(contentType_num_keep=1,contentType_num,null()),
        error_info_num=if(error_info_num_keep=1,error_info_num,null()),
        host_num=if(host_num_keep=1,host_num,null()),
        httpMethod_num=if(httpMethod_num_keep=1,httpMethod_num,null()),
        httpVersion_num=if(httpVersion_num_keep=1,httpVersion_num,null()),
        instanceId_num=if(instanceId_num_keep=1,instanceId_num,null()),
        originalHost_num=if(originalHost_num_keep=1,originalHost_num,null()),
        originalRequestUriWithArgs_num=if(originalRequestUriWithArgs_num_keep=1,originalRequestUriWithArgs_num,null()),
        requestUri_num=if(requestUri_num_keep=1,requestUri_num,null()),
        userAgent_num=if(userAgent_num_keep=1,userAgent_num,null()),
        WAFMode_num=if(WAFMode_num_keep=1,WAFMode_num,null())
| fields - *_keep
