index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1h
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus>=500)) as total_5xx_errors,
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate
| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error
| eval latency_spike = if(abs(delta_latency) > stdev_latency, 1, 0)
| eval error_spike = if(abs(delta_error) > stdev_error, 1, 0)
| eval severity_score = (avg_latency + rolling_error_rate + latency_spike + error_spike) * unique_clients

| eval future_error_count = lead(total_5xx_errors,5)
| eval future_count_500 = lead(count_500,5)
| eval future_count_502 = lead(count_502,5)
| eval future_count_503 = lead(count_503,5)
| eval future_count_504 = lead(count_504,5)

| where isnotnull(future_error_count)

| fields avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score total_5xx_errors count_500 count_502 count_503 count_504 unique_clients, future_error_count future_count_500 future_count_502 future_count_503 future_count_504

| fit GradientBoostingRegressor future_count_500 future_count_502 future_count_503 future_count_504 FROM avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients INTO FinalHttp5xxPredictor options n_estimators=300 learning_rate=0.8 max_depth=5




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus>=500)) as total_5xx_errors,
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time
| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate
| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error
| eval latency_spike = if(abs(delta_latency) > stdev_latency, 1, 0)
| eval error_spike = if(abs(delta_error) > stdev_error, 1, 0)
| eval severity_score = (avg_latency + rolling_error_rate + latency_spike + error_spike) * unique_clients

| apply FinalHttp5xxPredictor

| rename 
    predicted(future_count_500) as predicted_count_500, 
    predicted(future_count_502) as predicted_count_502,
    predicted(future_count_503) as predicted_count_503,
    predicted(future_count_504) as predicted_count_504

| eval forecast_time_est = strftime(_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, predicted_count_500, predicted_count_502, predicted_count_503, predicted_count_504, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, total_5xx_errors, unique_clients

| sort forecast_time_est desc
