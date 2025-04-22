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
    count(eval(httpStatus=502)) as count_502
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

| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1
| eval latency_sent_diff = avg_latency - (total_sent/1000)
| eval received_sent_ratio_change = received_to_sent_ratio - latency_to_sent_ratio
| eval latency_spike = if(latency_change > 20, 1, 0)
| eval data_drop = if(total_sent < sent_moving_avg*0.7, 1, 0)

| apply forecast_502_classifier_model

| eval future_502_risk = if('predicted(label)'=1, "DANGER", "SAFE")

/* Apply regressor for all rows (whether DANGER or SAFE),
   but we will later only consider DANGER rows to report forecast counts */
| apply forecast_502_regressor_model
| rename "predicted(label)" as forecasted_502_logcount

| eval forecasted_502_count = exp(forecasted_502_logcount) - 1
| eval forecasted_502_count = round(forecasted_502_count, 0)
| eval forecasted_502_count = if(forecasted_502_count<0, 0, forecasted_502_count)

| eval future_time = _time
| eval actual_time = _time + 300

| join type=left actual_time
    [
      search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval actual_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus=502
      | bin actual_time span=1m
      | stats count as actual_502_count by actual_time
    ]

| eval forecast_time_est = strftime(future_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval actual_time_est = strftime(actual_time, "%Y-%m-%d %I:%M:%S %p EST")

/* Optional: If you only want to see DANGER rows, uncomment below */
| where future_502_risk="DANGER"

| table forecast_time_est, actual_time_est, future_502_risk, forecasted_502_count, actual_502_count

| sort forecast_time_est desc