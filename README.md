index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-90m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=1m
| stats 
    count as total_http_status,
    count(eval(httpStatus=502)) as count_502
  by _time

| sort 0 _time

| streamstats window=5 sum(count_502) as rolling_5min_502
| streamstats window=10 sum(count_502) as rolling_10min_502
| streamstats window=5 avg(total_http_status) as rolling_5min_total

| eval error_rate_502 = if(rolling_5min_total>0, rolling_5min_502/rolling_5min_total, 0)

| delta rolling_5min_502 as delta_5min_502
| delta rolling_10min_502 as delta_10min_502

| eventstats stdev(rolling_5min_502) as stdev_5min_502
| eventstats stdev(rolling_10min_502) as stdev_10min_502

| eval spike_5min = if(abs(delta_5min_502) > stdev_5min_502, 1, 0)
| eval spike_10min = if(abs(delta_10min_502) > stdev_10min_502, 1, 0)

| eval severity_score = case(
    rolling_5min_502 >= 5, "High",
    rolling_5min_502 >= 3, "Medium",
    rolling_5min_502 >= 1, "Low",
    true(), "None"
)

| reverse
| streamstats window=5 sum(spike_5min) as future_spike_5min
| reverse

| eval future_502_spike = if(future_spike_5min>0,1,0)

| fields _time, rolling_5min_502, rolling_10min_502, delta_5min_502, delta_10min_502, error_rate_502, spike_5min, spike_10min, severity_score, future_502_spike

| fit GradientBoostingClassifier future_502_spike from rolling_5min_502 rolling_10min_502 delta_5min_502 delta_10min_502 error_rate_502 spike_5min spike_10min into FinalPolishedModel502 options loss="exponential" learning_rate=0.07 n_estimators=300





index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| bin _time span=1m
| stats 
    count as total_http_status,
    count(eval(httpStatus=502)) as count_502
  by _time

| sort 0 _time

| streamstats window=5 sum(count_502) as rolling_5min_502
| streamstats window=10 sum(count_502) as rolling_10min_502
| streamstats window=5 avg(total_http_status) as rolling_5min_total

| eval error_rate_502 = if(rolling_5min_total>0, rolling_5min_502/rolling_5min_total, 0)

| delta rolling_5min_502 as delta_5min_502
| delta rolling_10min_502 as delta_10min_502

| eventstats stdev(rolling_5min_502) as stdev_5min_502
| eventstats stdev(rolling_10min_502) as stdev_10min_502

| eval spike_5min = if(abs(delta_5min_502) > stdev_5min_502, 1, 0)
| eval spike_10min = if(abs(delta_10min_502) > stdev_10min_502, 1, 0)

| eval severity_score = case(
    rolling_5min_502 >= 5, "High",
    rolling_5min_502 >= 3, "Medium",
    rolling_5min_502 >= 1, "Low",
    true(), "None"
)

| apply FinalPolishedModel502

| rename "predicted(future_502_spike)" as predicted_502_spike

| eval forecast_time = _time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")
| eval verify_time = _time + 300
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p %Z")

| join type=left verify_time
    [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval httpStatus = tonumber(httpStatus)
    | where httpStatus=502
    | bin verify_time span=1m
    | stats count as actual_502_errors by verify_time
    ]

| eval result_type = case(
    isnull(actual_502_errors), null(),
    predicted_502_spike=1 AND actual_502_errors>0, "True Positive",
    predicted_502_spike=1 AND actual_502_errors=0, "False Positive",
    predicted_502_spike=0 AND actual_502_errors>0, "Missed Forecast",
    predicted_502_spike=0 AND actual_502_errors=0, "True Negative"
)

| eval auto_alert_score = case(
    severity_score="High" AND predicted_502_spike=1, "CRITICAL",
    severity_score="Medium" AND predicted_502_spike=1, "WARNING",
    severity_score="Low" AND predicted_502_spike=1, "INFO",
    true(), "NORMAL"
)

| table forecast_time_est, verify_time_est, predicted_502_spike, actual_502_errors, result_type, auto_alert_score, rolling_5min_502, rolling_10min_502, error_rate_502, delta_5min_502, delta_10min_502, severity_score

| sort forecast_time_est desc
