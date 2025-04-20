index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.connectionDuration output=connectionDuration
| spath path=body.properties.clientRequestBytes output=clientRequestBytes
| spath path=body.properties.serverResponseBytes output=serverResponseBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval serverResponseLatency = tonumber(serverResponseLatency)
| eval sentBytes = tonumber(sentBytes)
| eval receivedBytes = tonumber(receivedBytes)
| eval connectionDuration = tonumber(connectionDuration)
| eval clientRequestBytes = tonumber(clientRequestBytes)
| eval serverResponseBytes = tonumber(serverResponseBytes)

| eval server_response_ratio = serverResponseBytes / (clientRequestBytes + 1)

| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    avg(connectionDuration) as avg_connectionDuration,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    avg(clientRequestBytes) as avg_clientRequestBytes,
    avg(serverResponseBytes) as avg_serverResponseBytes,
    avg(server_response_ratio) as avg_server_response_ratio,
    count(eval(httpStatus=502)) as count_502,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=3 last(avg_latency) as latency_lag3

| streamstats current=f window=1 last(avg_connectionDuration) as connDuration_lag1
| streamstats current=f window=2 last(avg_connectionDuration) as connDuration_lag2
| streamstats current=f window=3 last(avg_connectionDuration) as connDuration_lag3

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(avg_connectionDuration) as connDuration_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| streamstats window=3 avg(avg_server_response_ratio) as response_ratio_moving_avg

| eval delta_latency = avg_latency - latency_lag1
| eval delta_connDuration = avg_connectionDuration - connDuration_lag1
| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)

| streamstats window=5 max(count_502) as future_5m_has_502
| streamstats window=10 max(count_502) as future_10m_has_502

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval raw_label = future_5m_502_count + future_10m_502_count
| eval regressor_label = log(raw_label + 1)
| eval classifier_label = if(future_5m_has_502>=1 OR future_10m_has_502>=1, 1, 0)

| fields _time 
    latency_lag1 latency_lag2 latency_lag3 
    connDuration_lag1 connDuration_lag2 connDuration_lag3 
    latency_moving_avg connDuration_moving_avg sent_moving_avg received_moving_avg response_ratio_moving_avg
    delta_latency delta_connDuration 
    latency_to_sent_ratio received_to_sent_ratio 
    classifier_label regressor_label

| fit RandomForestClassifier classifier_label from 
    latency_lag1 latency_lag2 latency_lag3 
    connDuration_lag1 connDuration_lag2 connDuration_lag3 
    latency_moving_avg connDuration_moving_avg sent_moving_avg received_moving_avg response_ratio_moving_avg
    delta_latency delta_connDuration 
    latency_to_sent_ratio received_to_sent_ratio 
    into forecast_502_classifier_model

| fit GradientBoostingRegressor regressor_label from 
    latency_lag1 latency_lag2 latency_lag3 
    connDuration_lag1 connDuration_lag2 connDuration_lag3 
    latency_moving_avg connDuration_moving_avg sent_moving_avg received_moving_avg response_ratio_moving_avg
    delta_latency delta_connDuration 
    latency_to_sent_ratio received_to_sent_ratio 
    into forecast_502_regressor_model







index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.connectionDuration output=connectionDuration
| spath path=body.properties.clientRequestBytes output=clientRequestBytes
| spath path=body.properties.serverResponseBytes output=serverResponseBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| eval serverResponseLatency = tonumber(serverResponseLatency)
| eval sentBytes = tonumber(sentBytes)
| eval receivedBytes = tonumber(receivedBytes)
| eval connectionDuration = tonumber(connectionDuration)
| eval clientRequestBytes = tonumber(clientRequestBytes)
| eval serverResponseBytes = tonumber(serverResponseBytes)

| eval server_response_ratio = serverResponseBytes / (clientRequestBytes + 1)

| bin _time span=1m

| stats 
    avg(serverResponseLatency) as avg_latency,
    avg(connectionDuration) as avg_connectionDuration,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    avg(clientRequestBytes) as avg_clientRequestBytes,
    avg(serverResponseBytes) as avg_serverResponseBytes,
    avg(server_response_ratio) as avg_server_response_ratio,
    count(eval(httpStatus=502)) as count_502,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=3 last(avg_latency) as latency_lag3

| streamstats current=f window=1 last(avg_connectionDuration) as connDuration_lag1
| streamstats current=f window=2 last(avg_connectionDuration) as connDuration_lag2
| streamstats current=f window=3 last(avg_connectionDuration) as connDuration_lag3

| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(avg_connectionDuration) as connDuration_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| streamstats window=3 avg(avg_server_response_ratio) as response_ratio_moving_avg

| eval delta_latency = avg_latency - latency_lag1
| eval delta_connDuration = avg_connectionDuration - connDuration_lag1
| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)

| apply forecast_502_classifier_model

| eval future_502_risk = if('predicted(classifier_label)'=1, "DANGER", "SAFE")

| where future_502_risk="DANGER"

| apply forecast_502_regressor_model
| rename "predicted(regressor_label)" as forecasted_log_502_count

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

| table forecast_time, forecast_time_est, verify_time_est, future_502_risk, forecasted_502_count, actual_502_count

| sort - forecast_time
