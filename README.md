index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=latency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| sort 0 _time

| streamstats current=f window=1 last(latency) as latency_lag1
| streamstats current=f window=1 last(sentBytes) as sentBytes_lag1
| streamstats current=f window=1 last(receivedBytes) as receivedBytes_lag1

| eval delta_latency = latency - latency_lag1
| eval delta_sent = sentBytes - sentBytes_lag1
| eval delta_received = receivedBytes - receivedBytes_lag1

| streamstats window=5 avg(latency) as rolling_avg_latency
| streamstats window=5 avg(sentBytes) as rolling_avg_sent
| streamstats window=5 avg(receivedBytes) as rolling_avg_received

| eval latency_to_sent_ratio = latency / (sentBytes + 1)
| eval received_to_sent_ratio = receivedBytes / (sentBytes + 1)

| streamstats window=5 sum(eval(latency > rolling_avg_latency * 1.5)) as recent_latency_spikes
| streamstats window=5 sum(eval(sentBytes < rolling_avg_sent * 0.8)) as recent_sent_drops

| eval is_502 = if(httpStatus=502, 1, 0)

| streamstats window=20 max(is_502) as future_20events_has_502
| streamstats window=20 sum(is_502) as future_20events_502_count

| eval label_classifier = if(future_20events_has_502>=1, 1, 0)
| eval raw_label_regressor = future_20events_502_count
| eval label_regressor = log(raw_label_regressor + 1)

| fields _time latency sentBytes receivedBytes delta_latency delta_sent delta_received rolling_avg_latency rolling_avg_sent rolling_avg_received latency_to_sent_ratio received_to_sent_ratio recent_latency_spikes recent_sent_drops label_classifier label_regressor

| fit RandomForestClassifier label_classifier from 
    latency sentBytes receivedBytes delta_latency delta_sent delta_received rolling_avg_latency rolling_avg_sent rolling_avg_received latency_to_sent_ratio received_to_sent_ratio recent_latency_spikes recent_sent_drops
    into forecast_502_classifier_event_model

| fit GradientBoostingRegressor label_regressor from 
    latency sentBytes receivedBytes delta_latency delta_sent delta_received rolling_avg_latency rolling_avg_sent rolling_avg_received latency_to_sent_ratio received_to_sent_ratio recent_latency_spikes recent_sent_drops
    into forecast_502_regressor_event_model



index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=latency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp

| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| sort 0 _time

| streamstats current=f window=1 last(latency) as latency_lag1
| streamstats current=f window=1 last(sentBytes) as sentBytes_lag1
| streamstats current=f window=1 last(receivedBytes) as receivedBytes_lag1

| eval delta_latency = latency - latency_lag1
| eval delta_sent = sentBytes - sentBytes_lag1
| eval delta_received = receivedBytes - receivedBytes_lag1

| streamstats window=5 avg(latency) as rolling_avg_latency
| streamstats window=5 avg(sentBytes) as rolling_avg_sent
| streamstats window=5 avg(receivedBytes) as rolling_avg_received

| eval latency_to_sent_ratio = latency / (sentBytes + 1)
| eval received_to_sent_ratio = receivedBytes / (sentBytes + 1)

| streamstats window=5 sum(eval(latency > rolling_avg_latency * 1.5)) as recent_latency_spikes
| streamstats window=5 sum(eval(sentBytes < rolling_avg_sent * 0.8)) as recent_sent_drops

| apply forecast_502_classifier_event_model
| eval future_502_risk = if('predicted(label_classifier)'=1, "DANGER", "SAFE")

| where future_502_risk="DANGER"

| apply forecast_502_regressor_event_model
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


