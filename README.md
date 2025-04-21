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

| streamstats current=f window=1 last(avg_latency) as serverResponseLatency_lag1
| streamstats current=f window=2 last(avg_latency) as serverResponseLatency_lag2
| streamstats current=f window=3 last(avg_latency) as serverResponseLatency_lag3

| streamstats current=f window=1 last(total_sent) as sentBytes_lag1
| streamstats current=f window=2 last(total_sent) as sentBytes_lag2
| streamstats current=f window=3 last(total_sent) as sentBytes_lag3

| streamstats current=f window=1 last(total_received) as receivedBytes_lag1
| streamstats current=f window=2 last(total_received) as receivedBytes_lag2
| streamstats current=f window=3 last(total_received) as receivedBytes_lag3

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg

| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1
| eval sent_change = total_sent - sentBytes_lag1
| eval received_change = total_received - receivedBytes_lag1

| streamstats window=5 max(count_502) as future_5m_has_502
| streamstats window=10 max(count_502) as future_10m_has_502

| eval label = if(future_5m_has_502>=1 OR future_10m_has_502>=1, 1, 0)

| fields _time serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3 sentBytes_lag1 sentBytes_lag2 sentBytes_lag3 receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3 latency_moving_avg sent_moving_avg received_moving_avg latency_to_sent_ratio received_to_sent_ratio latency_change sent_change received_change label

| fit RandomForestClassifier label from 
    serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3
    sentBytes_lag1 sentBytes_lag2 sentBytes_lag3
    receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3
    latency_moving_avg sent_moving_avg received_moving_avg
    latency_to_sent_ratio received_to_sent_ratio
    latency_change sent_change received_change
    into forecast_502_classifier_model




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
(same feature engineering as above)

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval raw_label = future_5m_502_count + future_10m_502_count
| eval label = log(raw_label + 1)  /* natural log scaling for stability */

| fields _time serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3 sentBytes_lag1 sentBytes_lag2 sentBytes_lag3 receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3 latency_moving_avg sent_moving_avg received_moving_avg latency_to_sent_ratio received_to_sent_ratio latency_change sent_change received_change label

| fit GradientBoostingRegressor label from 
    serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3
    sentBytes_lag1 sentBytes_lag2 sentBytes_lag3
    receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3
    latency_moving_avg sent_moving_avg received_moving_avg
    latency_to_sent_ratio received_to_sent_ratio
    latency_change sent_change received_change
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

| streamstats current=f window=1 last(avg_latency) as serverResponseLatency_lag1
| streamstats current=f window=2 last(avg_latency) as serverResponseLatency_lag2
| streamstats current=f window=3 last(avg_latency) as serverResponseLatency_lag3

| streamstats current=f window=1 last(total_sent) as sentBytes_lag1
| streamstats current=f window=2 last(total_sent) as sentBytes_lag2
| streamstats current=f window=3 last(total_sent) as sentBytes_lag3

| streamstats current=f window=1 last(total_received) as receivedBytes_lag1
| streamstats current=f window=2 last(total_received) as receivedBytes_lag2
| streamstats current=f window=3 last(total_received) as receivedBytes_lag3

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg

| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1
| eval sent_change = total_sent - sentBytes_lag1
| eval received_change = total_received - receivedBytes_lag1

| apply forecast_502_classifier_model

| eval future_502_risk = if('predicted(label)'=1, "DANGER", "SAFE")

| where future_502_risk="DANGER"

| apply forecast_502_regressor_model
| rename "predicted(label)" as forecasted_log_502_count
| eval forecasted_502_count = exp(forecasted_log_502_count) - 1
| eval forecasted_502_count = round(forecasted_502_count, 0)
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

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, verify_time_est, future_502_risk, forecasted_502_count, actual_502_count

| sort forecast_time desc


