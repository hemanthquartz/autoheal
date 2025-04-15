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
| stats first(httpStatus) as httpStatus first(is_5xx) as error_5xx by _time, httpMethod, userAgent, backendPoolName

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

| where actual=1 OR forecasted=1

| table _time, httpStatus, actual, forecasted, match, httpMethod, backendPoolName, userAgent
| eventstats count as total
| stats count(eval(match="✔")) as correct, values(total) as total
| eval accuracy = round((correct / total) * 100, 2)