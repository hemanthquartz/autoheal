index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
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
    count(eval(httpStatus=502)) as count_502,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats window=5 avg(avg_latency) as moving_avg_latency
| streamstats window=5 stdev(avg_latency) as moving_latency_volatility
| streamstats window=5 avg(total_sent) as moving_avg_sent
| streamstats window=5 stdev(total_sent) as moving_sent_volatility
| streamstats window=5 avg(total_received) as moving_avg_received
| streamstats window=5 stdev(total_received) as moving_received_volatility

| eval latency_spike = if(avg_latency > (moving_avg_latency + 2 * moving_latency_volatility), 1, 0)
| eval sent_drop = if(total_sent < (moving_avg_sent - 2 * moving_sent_volatility), 1, 0)
| eval received_drop = if(total_received < (moving_avg_received - 2 * moving_received_volatility), 1, 0)
| eval stress_score = latency_spike + sent_drop + received_drop

| streamstats window=5 sum(count_502) as future_5xx_errors
| eval label = future_5xx_errors

| fields _time moving_avg_latency moving_latency_volatility moving_avg_sent moving_sent_volatility moving_avg_received moving_received_volatility latency_spike sent_drop received_drop stress_score label

| fit GradientBoostingRegressor label from 
    moving_avg_latency moving_latency_volatility 
    moving_avg_sent moving_sent_volatility 
    moving_avg_received moving_received_volatility 
    latency_spike sent_drop received_drop stress_score
    options:
      n_estimators=300
      learning_rate=0.05
      max_depth=5
    into forecast_502_regressor_model





index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
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
    count(eval(httpStatus=502)) as count_502,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats window=5 avg(avg_latency) as moving_avg_latency
| streamstats window=5 stdev(avg_latency) as moving_latency_volatility
| streamstats window=5 avg(total_sent) as moving_avg_sent
| streamstats window=5 stdev(total_sent) as moving_sent_volatility
| streamstats window=5 avg(total_received) as moving_avg_received
| streamstats window=5 stdev(total_received) as moving_received_volatility

| eval latency_spike = if(avg_latency > (moving_avg_latency + 2 * moving_latency_volatility), 1, 0)
| eval sent_drop = if(total_sent < (moving_avg_sent - 2 * moving_sent_volatility), 1, 0)
| eval received_drop = if(total_received < (moving_avg_received - 2 * moving_received_volatility), 1, 0)
| eval stress_score = latency_spike + sent_drop + received_drop

| apply forecast_502_regressor_model
| rename "predicted(label)" as forecasted_502_count

| eval forecasted_502_count = if(forecasted_502_count<0, 0, forecasted_502_count)

| eval forecast_time = _time
| eval verify_time = _time + 300

| join type=left verify_time
    [
      search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus=502
      | bin verify_time span=1m
      | stats count as actual_502_count by verify_time
    ]

| eval is_future = if(verify_time > now(), 1, 0)
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, verify_time_est, forecasted_502_count, actual_502_count, is_future

| sort - is_future forecast_time desc
