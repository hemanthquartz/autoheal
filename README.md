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

| reverse
| streamstats window=5 current=f last(count_500) as future_count_500
| streamstats window=5 current=f last(count_502) as future_count_502
| streamstats window=5 current=f last(count_503) as future_count_503
| streamstats window=5 current=f last(count_504) as future_count_504
| reverse

| where isnotnull(future_count_500)

| fields avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients future_count_500 future_count_502 future_count_503 future_count_504

| fit GradientBoostingRegressor future_count_500 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients into FinalModel_500 options n_estimators=300 learning_rate=0.8 max_depth=5

| fit GradientBoostingRegressor future_count_502 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients into FinalModel_502 options n_estimators=300 learning_rate=0.8 max_depth=5

| fit GradientBoostingRegressor future_count_503 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients into FinalModel_503 options n_estimators=300 learning_rate=0.8 max_depth=5

| fit GradientBoostingRegressor future_count_504 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score unique_clients into FinalModel_504 options n_estimators=300 learning_rate=0.8 max_depth=5