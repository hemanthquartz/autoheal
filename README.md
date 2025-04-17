index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval is_500 = if(httpStatus >= 500, 1, 0)

| bin _time span=30s
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(body.properties.clientIp) as unique_clients
  by _time
| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(delta_latency > 0.1 AND delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > 0.2 AND delta_error > stdev_error, 1, 0)

| eval severity_score = avg_latency * rolling_error_rate

| reverse
| streamstats window=20 sum(error_count) as future_500_error_count
| reverse

| eval future_500 = if(future_500_error_count>=1 OR (rolling_error_rate>1.5 AND latency_spike=1) OR error_spike=1, 1, 0)

| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| fields _time, future_500, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, hour, minute, unique_clients

| fit GradientBoostingClassifier future_500 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score into GBoostModel500Sensitive options loss="exponential"



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=30s
| stats 
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus >= 500)) as error_count,
    dc(body.properties.clientIp) as unique_clients
  by _time
| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(error_count) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(delta_latency > 0.1 AND delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > 0.2 AND delta_error > stdev_error, 1, 0)

| eval severity_score = avg_latency * rolling_error_rate

| eval hour=strftime(_time, "%H"), minute=strftime(_time, "%M")
| fields _time, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, hour, minute, unique_clients

| apply GBoostModel500Sensitive

| rename _time as forecast_time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")

| table forecast_time_est, 'predicted(future_500)', probability(future_500), avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, unique_clients
| sort forecast_time_est desc