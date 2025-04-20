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
    count as total_http_status,
    count(eval(httpStatus>=500)) as total_5xx_errors,
    count(eval(httpStatus=500)) as count_500,
    count(eval(httpStatus=502)) as count_502,
    count(eval(httpStatus=503)) as count_503,
    count(eval(httpStatus=504)) as count_504,
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

| apply forecast_502_model

| eval future_502 = if('predicted(label)'=1, 1, 0)

| rename _time as forecast_time
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time = forecast_time + 300

| join type=left verify_time
    [
      search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval verify_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus=502
      | bin verify_time span=1m
      | stats 
          values(httpStatus) as actual_http_status,
          count(eval(httpStatus=500)) as count_500_actual,
          count(eval(httpStatus=502)) as count_502_actual,
          count(eval(httpStatus=503)) as count_503_actual,
          count(eval(httpStatus=504)) as count_504_actual
      by verify_time
    ]

| eval verify_time_est = strftime(verify_time, "%Y-%m-%d %I:%M:%S %p EST")

| eval result_type = case(
    isnull(actual_http_status), null(),
    future_502=1 AND isnotnull(actual_http_status), "True Positive",
    future_502=1 AND isnull(actual_http_status), "False Positive",
    future_502=0 AND isnotnull(actual_http_status), "Missed Forecast",
    future_502=0 AND isnull(actual_http_status), "True Negative"
)

| table forecast_time_est, verify_time_est, future_502, actual_http_status, result_type, 
        count_500, count_502, count_503, count_504,
        count_500_actual, count_502_actual, count_503_actual, count_504_actual,
        avg_latency, latency_moving_avg, latency_change, received_to_sent_ratio, latency_to_sent_ratio,
        total_5xx_errors, total_http_status, unique_clients

| sort forecast_time_est desc