index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=latency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=5s

| stats 
    avg(latency) as avg_latency,
    max(latency) as max_latency,
    min(latency) as min_latency,
    avg(sentBytes) as avg_sentBytes,
    avg(receivedBytes) as avg_receivedBytes,
    count(eval(httpStatus=502)) as count_502_in_bin,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as avg_latency_lag1
| streamstats current=f window=1 last(avg_sentBytes) as avg_sentBytes_lag1
| streamstats current=f window=1 last(avg_receivedBytes) as avg_receivedBytes_lag1

| eval delta_avg_latency = avg_latency - avg_latency_lag1
| eval delta_avg_sent = avg_sentBytes - avg_sentBytes_lag1
| eval delta_avg_received = avg_receivedBytes - avg_receivedBytes_lag1

| streamstats window=3 avg(avg_latency) as rolling_latency_avg
| streamstats window=3 avg(avg_sentBytes) as rolling_sent_avg
| streamstats window=3 avg(avg_receivedBytes) as rolling_received_avg

| eval latency_to_sent_ratio = avg_latency / (avg_sentBytes + 1)
| eval received_to_sent_ratio = avg_receivedBytes / (avg_sentBytes + 1)

| streamstats window=5 sum(count_502_in_bin) as future_5bins_502_count
| streamstats window=5 max(count_502_in_bin) as future_5bins_has_502

| eval label_classifier = if(future_5bins_has_502>=1, 1, 0)
| eval raw_label_regressor = future_5bins_502_count
| eval label_regressor = log(raw_label_regressor + 1)

| fields _time avg_latency avg_sentBytes avg_receivedBytes max_latency min_latency delta_avg_latency delta_avg_sent delta_avg_received rolling_latency_avg rolling_sent_avg rolling_received_avg latency_to_sent_ratio received_to_sent_ratio label_classifier label_regressor

| fit RandomForestClassifier label_classifier from 
    avg_latency avg_sentBytes avg_receivedBytes max_latency min_latency delta_avg_latency delta_avg_sent delta_avg_received rolling_latency_avg rolling_sent_avg rolling_received_avg latency_to_sent_ratio received_to_sent_ratio
    into forecast_502_classifier_5s_model

| fit GradientBoostingRegressor label_regressor from 
    avg_latency avg_sentBytes avg_receivedBytes max_latency min_latency delta_avg_latency delta_avg_sent delta_avg_received rolling_latency_avg rolling_sent_avg rolling_received_avg latency_to_sent_ratio received_to_sent_ratio
    into forecast_502_regressor_5s_model




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=latency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=5s

| stats 
    avg(latency) as avg_latency,
    max(latency) as max_latency,
    min(latency) as min_latency,
    avg(sentBytes) as avg_sentBytes,
    avg(receivedBytes) as avg_receivedBytes,
    count(eval(httpStatus=502)) as count_502_in_bin,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as avg_latency_lag1
| streamstats current=f window=1 last(avg_sentBytes) as avg_sentBytes_lag1
| streamstats current=f window=1 last(avg_receivedBytes) as avg_receivedBytes_lag1

| eval delta_avg_latency = avg_latency - avg_latency_lag1
| eval delta_avg_sent = avg_sentBytes - avg_sentBytes_lag1
| eval delta_avg_received = avg_receivedBytes - avg_receivedBytes_lag1

| streamstats window=3 avg(avg_latency) as rolling_latency_avg
| streamstats window=3 avg(avg_sentBytes) as rolling_sent_avg
| streamstats window=3 avg(avg_receivedBytes) as rolling_received_avg

| eval latency_to_sent_ratio = avg_latency / (avg_sentBytes + 1)
| eval received_to_sent_ratio = avg_receivedBytes / (avg_sentBytes + 1)

| apply forecast_502_classifier_5s_model
| eval future_502_risk = if('predicted(label_classifier)'=1, "DANGER", "SAFE")

| where future_502_risk="DANGER"

| apply forecast_502_regressor_5s_model
| rename "predicted(label_regressor)" as forecasted_log_502_count
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
      | stats count as actual_502_count by verify_time
    ]

| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est, verify_time_est, future_502_risk, forecasted_502_count, actual_502_count

| sort forecast_time desc


