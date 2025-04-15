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

| where forecasted=1

| eval match = if(actual == forecasted, "✔", "✖")
| table _time, actual_http_status, actual, forecasted, match, httpMethod, backendPoolName, userAgent
| eventstats count as total_forecasted
| stats count as forecasted_count values(total_forecasted) as total
| eval accuracy = round((forecasted_count / total) * 100, 2)