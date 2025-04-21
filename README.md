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
| streamstats current=f window=5 last(count_502) as error_lag5

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=5 avg(avg_latency) as latency_moving_avg_5
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=5 avg(total_sent) as sent_moving_avg_5
| streamstats window=3 avg(total_received) as received_moving_avg
| streamstats window=5 avg(total_received) as received_moving_avg_5
| streamstats window=3 sum(count_502) as error_moving_sum
| streamstats window=5 sum(count_502) as error_moving_sum_5

| eval latency_spike_ratio = (avg_latency - latency_lag1) / (latency_lag1 + 1)
| eval sent_bytes_percent_change = (sent_lag1 - sent_lag2) / (sent_lag2 + 1)
| eval sent_bytes_trend = (sent_moving_avg_5 - sent_moving_avg) / (sent_moving_avg + 1)
| eval received_bytes_percent_change = (received_lag1 - received_lag2) / (received_lag2 + 1)
| eval received_bytes_trend = (received_moving_avg_5 - received_moving_avg) / (received_moving_avg + 1)
| eval latency_vs_sent_ratio = avg_latency / (total_sent + 1)
| eval traffic_stability = abs(total_sent - total_received) / (total_sent + 1)
| eval error_rate = count_502 / (total_requests + 1)
| eval error_trend = (error_moving_sum_5 - error_moving_sum) / (error_moving_sum + 1)
| eval latency_p95_ratio = p95_latency / (avg_latency + 1)
| eval client_density = unique_clients / (total_requests + 1)
| eval hour_of_day = strftime(_time, "%H")
| eval is_peak_hour = case(hour_of_day >= 9 AND hour_of_day <= 17, 1, true(), 0)

| eval is_502 = if(httpStatus=502, 1, 0)
| streamstats window=3 sum(is_502) as error_velocity
| eval traffic_stress_index = (latency_spike_ratio + sent_bytes_percent_change + received_bytes_percent_change + error_rate) / 4

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval raw_label = future_5m_502_count + future_10m_502_count
| eval label = raw_label
| eval binary_label = if(raw_label > 0, 1, 0)

| fields _time latency_spike_ratio sent_bytes_percent_change sent_bytes_trend received_bytes_percent_change 
         received_bytes_trend latency_vs_sent_ratio traffic_stability latency_moving_avg 
         sent_moving_avg received_moving_avg error_velocity traffic_stress_index error_rate 
         error_trend latency_p95_ratio client_density max_latency is_peak_hour binary_label label

| fit GradientBoostingRegressor label from 
    latency_spike_ratio sent_bytes_percent_change sent_bytes_trend received_bytes_percent_change
    received_bytes_trend latency_vs_sent_ratio traffic_stability latency_moving_avg sent_moving_avg 
    received_moving_avg error_velocity traffic_stress_index error_rate error_trend 
    latency_p95_ratio client_density max_latency is_peak_hour
    max_depth=3 learning_rate=0.1 n_estimators=100 min_samples_split=10
    into forecast_502_regressor_model_v4

| fit LogisticRegression binary_label from 
    latency_spike_ratio sent_bytes_percent_change sent_bytes_trend received_bytes_percent_change
    received_bytes_trend latency_vs_sent_ratio traffic_stability latency_moving_avg sent_moving_avg 
    received_moving_avg error_velocity traffic_stress_index error_rate error_trend 
    latency_p95_ratio client_density max_latency is_peak_hour
    fit_intercept=true
    into forecast_502_classifier_model_v4