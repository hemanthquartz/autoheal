no index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| sort _time
| streamstats count as row_number
| eventstats max(row_number) as total_rows
| eval split_point = round(total_rows * 0.8)
| eval dataset = if(row_number <= split_point, "train", "forecast")
| where dataset="train"
| eval label = is_5xx
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| fit RandomForestClassifier label from httpMethod, userAgent, backendPoolName, hour, day into http_error_forecast_model



index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| sort _time
| streamstats count as row_number
| eventstats max(row_number) as total_rows
| eval split_point = round(total_rows * 0.8)
| eval dataset = if(row_number <= split_point, "train", "forecast")
| where dataset="forecast"
| eval label = is_5xx
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| apply http_error_forecast_model
| eval match = if(label == 'predicted(label)', 1, 0)
| eventstats count as total_forecast
| stats count(eval(match=1)) as correct count as total
| eval accuracy = round((correct / total) * 100, 2)
| fields accuracy, correct, total
| appendpipe [
    | confusionmatrix label predicted(label)
]

| appendpipe [
    | stats count by label, 'predicted(label)'
]



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
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| rename is_5xx as label
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
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| rename is_5xx as actual
| apply http_error_forecast_model
| rename "predicted(label)" as forecasted
| eval match = if(actual==forecasted, "✔", "✖")
| table _time, httpMethod, backendPoolName, actual, forecasted, match
| eventstats count(eval(match="✔")) as correct count as total
| eval accuracy = round((correct / total) * 100, 2)



| eval match = if(actual == forecasted, 1, 0)
| eventstats count as total
| stats count(eval(match=1)) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-48h latest=-24h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| rename is_5xx as label
| fit RandomForestClassifier label from httpMethod, userAgent, backendPoolName, hour, day into http_error_forecast_model


index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| rename is_5xx as actual
| apply http_error_forecast_model
| rename "predicted(label)" as forecasted
| eval match = if(actual == forecasted, 1, 0)
| eventstats count as total
| stats count(eval(match=1)) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)
__________________________________________________________________________________________________________________
index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-48h latest=-24h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)

| bin _time span=5m
| stats sum(is_5xx) as error_5xx by _time, httpMethod, userAgent, backendPoolName

| sort 0 _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3

| eval hour=strftime(_time, "%H"), day=strftime(_time, "%A")
| eval weekend=if(day="Saturday" OR day="Sunday", 1, 0)

| eval label=if(error_5xx > 0, 1, 0)
| eval httpMethod=coalesce(httpMethod, "unknown")
| eval userAgent=coalesce(userAgent, "unknown")
| eval backendPoolName=coalesce(backendPoolName, "unknown")

| fields _time, label, lag_1, lag_2, lag_3, httpMethod, userAgent, backendPoolName, hour, day, weekend

| fit RandomForestClassifier label from lag_1, lag_2, lag_3, httpMethod, userAgent, backendPoolName, hour, day, weekend into http_forecast_model_v2




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)

| bin _time span=5m
| stats sum(is_5xx) as error_5xx by _time, httpMethod, userAgent, backendPoolName

| sort 0 _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3

| eval hour=strftime(_time, "%H"), day=strftime(_time, "%A")
| eval weekend=if(day="Saturday" OR day="Sunday", 1, 0)
| eval label=if(error_5xx > 0, 1, 0)
| eval httpMethod=coalesce(httpMethod, "unknown")
| eval userAgent=coalesce(userAgent, "unknown")
| eval backendPoolName=coalesce(backendPoolName, "unknown")

| apply http_forecast_model_v2
| rename "predicted(label)" as forecasted, label as actual

| eval match=if(actual==forecasted, "✔", "✖")
| table _time, actual, forecasted, match, httpMethod, backendPoolName, userAgent

| eventstats count as total
| stats count(eval(match="✔")) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)

| eval accuracy=round((correct / total) * 100, 2)
| appendpipe [| confusionmatrix actual forecasted]
________________________________________________________________________________________________

index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")

| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)

| bin _time span=5m
| stats sum(is_5xx) as error_5xx values(httpStatus) as actual_http_status by _time, httpMethod, userAgent, backendPoolName

| sort 0 _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3

| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| eval weekend = if(day="Saturday" OR day="Sunday", 1, 0)
| eval label = if(error_5xx > 0, 1, 0)

| eval httpMethod = coalesce(httpMethod, "unknown")
| eval userAgent = coalesce(userAgent, "unknown")
| eval backendPoolName = coalesce(backendPoolName, "unknown")

| apply http_forecast_model_v2
| rename "predicted(label)" as forecasted, label as actual

| eval match = if(actual == forecasted, "✔", "✖")

| table _time, actual_http_status, actual, forecasted, match, httpMethod, backendPoolName, userAgent

| eventstats count as total
| stats count(eval(match="✔")) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)
