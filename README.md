index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.clientIp output=clientIp
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    max(serverResponseLatency) as max_latency,
    p95(serverResponseLatency) as p95_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus>=500)) as count_5xx,
    dc(clientIp) as unique_clients,
    count as total_requests
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=5 last(avg_latency) as latency_lag5
| streamstats current=f window=1 last(total_sent) as sent_lag1
| streamstats current=f window=2 last(total_sent) as sent_lag2
| streamstats current=f window=5 last(total_sent) as sent_lag5
| streamstats current=f window=1 last(total_received) as received_lag1
| streamstats current=f window=2 last(total_received) as received_lag2
| streamstats current=f window=5 last(total_received) as received_lag5
| streamstats current=f window=1 last(count_502) as error_lag1
| streamstats current=f window=2 last(count_502) as error_lag2

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=5 avg(avg_latency) as latency_moving_avg_5
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| streamstats window=3 sum(count_502) as error_moving_sum

| eval latency_spike_ratio = (avg_latency - latency_lag1) / (latency_lag1 + 1)
| eval sent_bytes_percent_change = (sent_lag1 - sent_lag2) / (sent_lag2 + 1)
| eval received_bytes_percent_change = (received_lag1 - received_lag2) / (received_lag2 + 1)
| eval latency_vs_sent_ratio = avg_latency / (total_sent + 1)
| eval traffic_stability = abs(total_sent - total_received) / (total_sent + 1)
| eval error_rate = count_502 / (total_requests + 1)
| eval latency_p95_ratio = p95_latency / (avg_latency + 1)
| eval client_density = unique_clients / (total_requests + 1)

| eval is_502 = if(httpStatus=502, 1, 0)
| streamstats window=3 sum(is_502) as error_velocity
| eval traffic_stress_index = (latency_spike_ratio + sent_bytes_percent_change + received_bytes_percent_change + error_rate) / 4

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval raw_label = future_5m_502_count + future_10m_502_count
| eval label = if(raw_label > 0, log(raw_label + 1), 0)
| eval binary_label = if(raw_label > 0, 1, 0)

| fields _time latency_spike_ratio sent_bytes_percent_change received_bytes_percent_change 
         latency_vs_sent_ratio traffic_stability latency_moving_avg sent_moving_avg 
         received_moving_avg error_velocity traffic_stress_index error_rate 
         latency_p95_ratio client_density max_latency binary_label label

| fit GradientBoostingRegressor label from 
    latency_spike_ratio sent_bytes_percent_change received_bytes_percent_change
    latency_vs_sent_ratio traffic_stability latency_moving_avg sent_moving_avg 
    received_moving_avg error_velocity traffic_stress_index error_rate 
    latency_p95_ratio client_density max_latency
    max_depth=5 learning_rate=0.05 n_estimators=200 min_samples_split=5
    into forecast_502_regressor_model_v3

| fit RandomForestClassifier binary_label from 
    latency_spike_ratio sent_bytes_percent_change received_bytes_percent_change
    latency_vs_sent_ratio traffic_stability latency_moving_avg sent_moving_avg 
    received_moving_avg error_velocity traffic_stress_index error_rate 
    latency_p95_ratio client_density max_latency
    max_depth=10 n_estimators=100 min_samples_split=5 class_weight=balanced
    into forecast_502_classifier_model_v3




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.clientIp output=clientIp
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    max(serverResponseLatency) as max_latency,
    p95(serverResponseLatency) as p95_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus>=500)) as count_5xx,
    dc(clientIp) as unique_clients,
    count as total_requests
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=5 last(avg_latency) as latency_lag5
| streamstats current=f window=1 last(total_sent) as sent_lag1
| streamstats current=f window=2 last(total_sent) as sent_lag2
| streamstats current=f window=5 last(total_sent) as sent_lag5
| streamstats current=f window=1 last(total_received) as received_lag1
| streamstats current=f window=2 last(total_received) as received_lag2
| streamstats current=f window=5 last(total_received) as received_lag5
| streamstats current=f window=1 last(count_502) as error_lag1
| streamstats current=f window=2 last(count_502) as error_lag2

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=5 avg(avg_latency) as latency_moving_avg_5
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| streamstats window=3 sum(count_502) as error_moving_sum

| eval latency_spike_ratio = (avg_latency - latency_lag1) / (latency_lag1 + 1)
| eval sent_bytes_percent_change = (sent_lag1 - sent_lag2) / (sent_lag2 + 1)
| eval received_bytes_percent_change = (received_lag1 - received_lag2) / (received_lag2 + 1)
| eval latency_vs_sent_ratio = avg_latency / (total_sent + 1)
| eval traffic_stability = abs(total_sent - total_received) / (total_sent + 1)
| eval error_rate = count_502 / (total_requests + 1)
| eval latency_p95_ratio = p95_latency / (avg_latency + 1)
| eval client_density = unique_clients / (total_requests + 1)

| eval is_502 = if(httpStatus=502, 1, 0)
| streamstats window=3 sum(is_502) as error_velocity
| eval traffic_stress_index = (latency_spike_ratio + sent_bytes_percent_change + received_bytes_percent_change + error_rate) / 4

| apply forecast_502_classifier_model_v3
| eval future_502_risk = if('predicted(binary_label)'=1, "DANGER", "SAFE")

| where future_502_risk="DANGER"

| apply forecast_502_regressor_model_v3
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

| eval prediction_error = abs(forecasted_502_count - actual_502_count)
| eval prediction_accuracy = if(actual_502_count > 0, 1 - (prediction_error / actual_502_count), 1)

| table forecast_time_est, verify_time_est, future_502_risk, forecasted_502_count, actual_502_count, prediction_accuracy

| sort -forecast_time
