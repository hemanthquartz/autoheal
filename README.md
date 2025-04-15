index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-48h latest=-24h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.properties.backendResponseLatency output=backendLatency
| spath path=body.timeStamp output=timestamp

| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H")
| eval day = strftime(_time, "%A")
| eval weekend = if(day IN ("Saturday", "Sunday"), 1, 0)

| eval latency = coalesce(backendLatency, 0)
| eval httpMethod = coalesce(httpMethod, "unknown")
| eval userAgent = coalesce(userAgent, "unknown")
| eval userAgent_class = case(
    match(userAgent, "curl|bot|crawler"), "bot",
    match(userAgent, "Mozilla"), "browser",
    match(userAgent, "GitHub"), "github",
    true(), "other"
)
| eval backendPoolName = coalesce(backendPoolName, "unknown")

| bin _time span=5m
| stats sum(is_5xx) as error_5xx avg(latency) as latency by _time, httpMethod, userAgent_class, backendPoolName, hour, day, weekend

| sort 0 _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3
| streamstats current=f window=4 last(error_5xx) as lag_4
| streamstats current=f window=5 last(error_5xx) as lag_5

| eval rolling_avg_5xx = (coalesce(lag_1,0) + lag_2 + lag_3 + lag_4 + lag_5) / 5
| eval burst_score = if((lag_1 >= 1 AND lag_2 >= 1) OR (lag_3 >= 2), 1, 0)

| eventstats count by backendPoolName
| rename count as backendPool_freq

| eval label = if(error_5xx > 0, 1, 0)

| fit RandomForestClassifier label from rolling_avg_5xx, burst_score, latency, backendPool_freq, httpMethod, userAgent_class, backendPoolName, hour, day, weekend into http_forecast_model_ultimate




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-24h latest=now
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.httpMethod output=httpMethod
| spath path=body.properties.userAgent output=userAgent
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.properties.backendResponseLatency output=backendLatency
| spath path=body.timeStamp output=timestamp

| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H")
| eval day = strftime(_time, "%A")
| eval weekend = if(day IN ("Saturday", "Sunday"), 1, 0)

| eval latency = coalesce(backendLatency, 0)
| eval httpMethod = coalesce(httpMethod, "unknown")
| eval userAgent = coalesce(userAgent, "unknown")
| eval userAgent_class = case(
    match(userAgent, "curl|bot|crawler"), "bot",
    match(userAgent, "Mozilla"), "browser",
    match(userAgent, "GitHub"), "github",
    true(), "other"
)
| eval backendPoolName = coalesce(backendPoolName, "unknown")

| bin _time span=5m
| eventstats sum(is_5xx) as error_5xx avg(latency) as latency by _time
| streamstats current=f window=1 last(error_5xx) as lag_1
| streamstats current=f window=2 last(error_5xx) as lag_2
| streamstats current=f window=3 last(error_5xx) as lag_3
| streamstats current=f window=4 last(error_5xx) as lag_4
| streamstats current=f window=5 last(error_5xx) as lag_5

| eval rolling_avg_5xx = (coalesce(lag_1,0) + lag_2 + lag_3 + lag_4 + lag_5) / 5
| eval burst_score = if((lag_1 >= 1 AND lag_2 >= 1) OR (lag_3 >= 2), 1, 0)

| eventstats count by backendPoolName
| rename count as backendPool_freq

| eval label = if(is_5xx == 1, 1, 0)

| apply http_forecast_model_ultimate
| rename "predicted(label)" as forecasted, label as actual

| eval match = if(actual == forecasted, "✔", "✖")
| eval forecast_event = if(forecasted == 1 AND actual == 0, "⚠️ Forecasted 5xx", null())
| eval actual_5xx = if(httpStatus >= 500, "🟥 Actual 5xx", null())

| where httpStatus >= 500 OR forecasted = 1

| table _time, httpStatus, actual, forecasted, match, forecast_event, actual_5xx, backendPoolName, httpMethod, userAgent_class, rolling_avg_5xx, latency, burst_score

| eval true_positive = if(httpStatus >= 500 AND forecasted == 1, 1, 0)
| eval false_negative = if(httpStatus >= 500 AND forecasted == 0, 1, 0)
| eval false_positive = if(httpStatus < 500 AND forecasted == 1, 1, 0)

| eventstats count as total
| stats 
    count(eval(httpStatus >= 500)) as total_5xx,
    count(eval(true_positive == 1)) as correct,
    count(eval(false_negative == 1)) as missed,
    count(eval(false_positive == 1)) as false_alerts,
    values(total) as total_tested
| eval accuracy = round((correct / total_5xx) * 100, 2)

