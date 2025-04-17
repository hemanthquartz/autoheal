index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-30m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| where httpStatus >= 500
| bin _time span=1m

| stats 
    values(httpStatus) as all_http_status,
    count as total_5xx_errors,
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > stdev_error, 1, 0)

| eval severity_score = avg_latency * rolling_error_rate

| eval future_500 = if(total_5xx_errors>=1 OR (rolling_error_rate>0.5 AND latency_spike=1) OR error_spike=1, 1, 0)

| fields _time, future_500, avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score

| fit GradientBoostingClassifier future_500 from avg_latency rolling_avg_latency delta_latency rolling_error_rate delta_error latency_spike error_spike severity_score into GBoostModel500Sensitive options n_estimators=200 learning_rate=0.1 loss="exponential"




index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)

| where httpStatus >= 500
| bin _time span=1m

| stats 
    values(httpStatus) as all_http_status,
    count as total_5xx_errors,
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
    avg(serverResponseLatency) as avg_latency,
    sum(sentBytes) as total_sent,
    sum(receivedBytes) as total_received,
    dc(body.properties.clientIp) as unique_clients
  by _time

| sort 0 _time

| streamstats window=5 avg(avg_latency) as rolling_avg_latency
| streamstats window=5 avg(total_5xx_errors) as rolling_error_rate

| delta avg_latency as delta_latency
| delta rolling_error_rate as delta_error
| eventstats stdev(avg_latency) as stdev_latency
| eventstats stdev(rolling_error_rate) as stdev_error

| eval latency_spike = if(delta_latency > stdev_latency, 1, 0)
| eval error_spike = if(delta_error > stdev_error, 1, 0)

| eval severity_score = avg_latency * rolling_error_rate

| mvexpand all_http_status
| eval predicted_error_code = all_http_status

| apply GBoostModel500Sensitive

| rename _time as forecast_time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p %Z")
| eval verify_time = forecast_time + 600

| join type=left verify_time
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus >= 500
      | bin verify_time span=1m
      | stats 
          values(httpStatus) as actual_http_status,
          count(eval(httpStatus=500)) as count_500_actual,
          count(eval(httpStatus=502)) as count_502_actual,
          count(eval(httpStatus=503)) as count_503_actual,
          count(eval(httpStatus=504)) as count_504_actual
      by verify_time
    ]

| eval actual_http_status = mvindex(actual_http_status, 0)
| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p %Z")

| eval result_type = case(
    isnull(actual_http_status), null(),
    predicted_error_code=actual_http_status, "True Positive",
    isnotnull(predicted_error_code) AND isnull(actual_http_status), "False Positive",
    isnull(predicted_error_code) AND isnotnull(actual_http_status), "Missed Forecast",
    predicted_error_code != actual_http_status, "Wrong Code Predicted"
)

| eval count_500_forecasted = if(predicted_error_code=500, 1, 0)
| eval count_502_forecasted = if(predicted_error_code=502, 1, 0)
| eval count_503_forecasted = if(predicted_error_code=503, 1, 0)
| eval count_504_forecasted = if(predicted_error_code=504, 1, 0)

| table forecast_time_est, verify_time_est, predicted_error_code, actual_http_status, result_type, probability(future_500),
        count_500_forecasted, count_502_forecasted, count_503_forecasted, count_504_forecasted,
        count_500_actual, count_502_actual, count_503_actual, count_504_actual,
        avg_latency, rolling_avg_latency, delta_latency, rolling_error_rate, delta_error, latency_spike, error_spike, severity_score, total_5xx_errors, count_500, count_502, count_503, count_504, unique_clients
| sort forecast_time_est desc
