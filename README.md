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
| eval serverResponseLatency=tonumber(serverResponseLatency),
        timeTaken=tonumber(timeTaken),
        WAFEvaluationTime=tonumber(WAFEvaluationTime),
        httpStatus=tonumber(httpStatus),
        clientPort=tonumber(clientPort)
| where isnotnull(clientIP) OR isnotnull(clientPort) OR isnotnull(contentType) OR isnotnull(error_info) OR isnotnull(host)
    OR isnotnull(httpMethod) OR isnotnull(httpVersion) OR isnotnull(instanceId) OR isnotnull(originalHost)
    OR isnotnull(originalRequestUriWithArgs) OR isnotnull(requestUri) OR isnotnull(serverResponseLatency)
    OR isnotnull(timeTaken) OR isnotnull(userAgent) OR isnotnull(WAFEvaluationTime) OR isnotnull(WAFMode)
| table _time httpStatus clientIP clientPort contentType error_info host httpMethod httpVersion instanceId originalHost originalRequestUriWithArgs requestUri serverResponseLatency timeTaken userAgent WAFEvaluationTime WAFMode
