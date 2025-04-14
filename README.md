index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-48h latest=-24h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| eval label = is_5xx
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| table _time, label, httpMethod, userAgent, backendPoolName, hour, day
| fit RandomForestClassifier label from httpMethod, userAgent, backendPoolName, hour, day into http_error_forecast_model



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| eval label = is_5xx
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| table _time, label, httpMethod, userAgent, backendPoolName, hour, day
| apply http_error_forecast_model
| eval match = if(label == 'predicted(label)', 1, 0)
| eval result_type = if(label == 1 AND 'predicted(label)' == 1, "True Positive",
                if(label == 0 AND 'predicted(label)' == 1, "False Positive",
                if(label == 1 AND 'predicted(label)' == 0, "False Negative", "True Negative")))
| table _time, label, 'predicted(label)', result_type, httpMethod, backendPoolName, userAgent


| eventstats count as total
| stats count(eval(match=1)) as correct count as total
| eval accuracy = round((correct / total) * 100, 2)
| fields accuracy, correct, total
