index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval label = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour=strftime(_time,"%H"), day=strftime(_time,"%A")
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| table _time, label, httpMethod, userAgent, backendPoolName, hour, day
| fit RandomForestClassifier label from httpMethod, userAgent, backendPoolName, hour, day into http_5xx_forecast_model



index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval Actual_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour=strftime(_time,"%H"), day=strftime(_time,"%A")
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| table _time, Actual_5xx, httpMethod, userAgent, backendPoolName, hour, day
| apply http_5xx_forecast_model
| rename predicted(label) as Forecasted_5xx
| table _time, Actual_5xx, Forecasted_5xx, httpMethod, backendPoolName, userAgent, hour, day
| eval correct=if(Actual_5xx=Forecasted_5xx,1,0)
| eventstats count as total_events
| eventstats sum(correct) as total_correct
| eval accuracy=round((total_correct/total_events)*100,2)
| fields _time, Actual_5xx, Forecasted_5xx, accuracy, httpMethod, backendPoolName, userAgent, hour, day