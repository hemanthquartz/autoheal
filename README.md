index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-48h latest=-24h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.properties.serverResponseLatency output=serverLatency
| spath path=body.properties.backendResponseLatency output=backendLatency
| spath path=body.timeStamp output=timestamp

| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval is_client_error = if(httpStatus >= 400 AND httpStatus < 500, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A"), weekend = if(day IN ("Saturday", "Sunday"), 1, 0)
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| eval latency = coalesce(backendLatency, serverLatency, 0)

| bin _time span=5m
| stats sum(is_5xx) as error_5xx sum(is_client_error) as client_err avg(latency) as latency by _time, httpMethod, userAgent, backendPoolName, hour, day, weekend

| sort 0 _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3
| streamstats current=f window=4 last(error_5xx) as lag_4
| streamstats current=f window=5 last(error_5xx) as lag_5

| eval rolling_avg = (coalesce(lag_1,0) + lag_2 + lag_3 + lag_4 + lag_5) / 5
| eval label = if(error_5xx > 0, 1, 0)

| fit RandomForestClassifier label from rolling_avg, client_err, httpMethod, userAgent, backendPoolName, hour, day, weekend, latency into http_forecast_model_rf




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.properties.serverResponseLatency output=serverLatency
| spath path=body.properties.backendResponseLatency output=backendLatency
| spath path=body.timeStamp output=timestamp

| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval is_client_error = if(httpStatus >= 400 AND httpStatus < 500, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A"), weekend = if(day IN ("Saturday", "Sunday"), 1, 0)
| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown")
| eval latency = coalesce(backendLatency, serverLatency, 0)

| bin _time span=5m
| eventstats sum(is_5xx) as error_5xx sum(is_client_error) as client_err avg(latency) as latency by _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3
| streamstats current=f window=4 last(error_5xx) as lag_4
| streamstats current=f window=5 last(error_5xx) as lag_5

| eval rolling_avg = (coalesce(lag_1,0) + lag_2 + lag_3 + lag_4 + lag_5) / 5
| eval label = if(is_5xx == 1, 1, 0)

| apply http_forecast_model_rf
| rename "predicted(label)" as forecasted, label as actual
| eval match = if(actual == forecasted, "✔", "✖")

| where httpStatus >= 500 OR forecasted=1

| table _time, httpStatus, actual, forecasted, match, httpMethod, backendPoolName, userAgent

| eventstats count as total
| stats count(eval(match="✔")) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)
