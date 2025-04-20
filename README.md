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

| streamstats window=1 last(avg_latency) as serverResponseLatency_lag1
| streamstats window=2 last(avg_latency) as serverResponseLatency_lag2
| streamstats window=3 last(avg_latency) as serverResponseLatency_lag3

| streamstats window=1 last(total_sent) as sentBytes_lag1
| streamstats window=2 last(total_sent) as sentBytes_lag2
| streamstats window=3 last(total_sent) as sentBytes_lag3

| streamstats window=1 last(total_received) as receivedBytes_lag1
| streamstats window=2 last(total_received) as receivedBytes_lag2
| streamstats window=3 last(total_received) as receivedBytes_lag3

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg

| streamstats window=3 sum(count_502) as error_moving_sum
| streamstats window=3 avg(count_502) as error_moving_avg
| delta count_502 as error_delta

| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval label_regressor = future_5m_502_count + future_10m_502_count

| fields _time serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3 
    sentBytes_lag1 sentBytes_lag2 sentBytes_lag3
    receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3
    latency_moving_avg sent_moving_avg received_moving_avg
    latency_to_sent_ratio received_to_sent_ratio latency_change
    error_moving_sum error_moving_avg error_delta
    label_regressor

| fit GradientBoostingRegressor label_regressor from 
    serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3
    sentBytes_lag1 sentBytes_lag2 sentBytes_lag3
    receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3
    latency_moving_avg sent_moving_avg received_moving_avg
    latency_to_sent_ratio received_to_sent_ratio latency_change
    error_moving_sum error_moving_avg error_delta
    into forecast_502_regressor_model



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
(same feature prep)

| apply forecast_502_regressor_model
| rename "predicted(label_regressor)" as forecasted_502_count
| eval forecasted_502_count = round(forecasted_502_count, 0)
| eval forecasted_502_count = if(forecasted_502_count<0, 0, forecasted_502_count)
...
(join to real actual_502_count)
...
| table forecast_time, forecast_time_est, verify_time_est, forecasted_502_count, actual_502_count
| sort - forecast_time



