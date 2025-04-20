index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-2d
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

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=3 last(avg_latency) as latency_lag3
| streamstats current=f window=4 last(avg_latency) as latency_lag4
| streamstats current=f window=5 last(avg_latency) as latency_lag5

| streamstats current=f window=1 last(total_sent) as sent_lag1
| streamstats current=f window=2 last(total_sent) as sent_lag2
| streamstats current=f window=3 last(total_sent) as sent_lag3
| streamstats current=f window=4 last(total_sent) as sent_lag4
| streamstats current=f window=5 last(total_sent) as sent_lag5

| streamstats current=f window=1 last(total_received) as recv_lag1
| streamstats current=f window=2 last(total_received) as recv_lag2
| streamstats current=f window=3 last(total_received) as recv_lag3
| streamstats current=f window=4 last(total_received) as recv_lag4
| streamstats current=f window=5 last(total_received) as recv_lag5

| eval latency_change=avg_latency-latency_lag1
| eval sent_change=total_sent-sent_lag1
| eval recv_change=total_received-recv_lag1

| streamstats window=5 sum(count_502) as future_5m_502_count
| streamstats window=10 sum(count_502) as future_10m_502_count

| eval raw_label = future_5m_502_count + future_10m_502_count
| eval label = log(raw_label + 1)

| fields latency_lag* sent_lag* recv_lag* latency_change sent_change recv_change label

| fit GradientBoostingRegressor label from *
  into final_refined_502_regressor




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

| streamstats current=f window=1 last(avg_latency) as latency_lag1
| streamstats current=f window=2 last(avg_latency) as latency_lag2
| streamstats current=f window=3 last(avg_latency) as latency_lag3
| streamstats current=f window=4 last(avg_latency) as latency_lag4
| streamstats current=f window=5 last(avg_latency) as latency_lag5

| streamstats current=f window=1 last(total_sent) as sent_lag1
| streamstats current=f window=2 last(total_sent) as sent_lag2
| streamstats current=f window=3 last(total_sent) as sent_lag3
| streamstats current=f window=4 last(total_sent) as sent_lag4
| streamstats current=f window=5 last(total_sent) as sent_lag5

| streamstats current=f window=1 last(total_received) as recv_lag1
| streamstats current=f window=2 last(total_received) as recv_lag2
| streamstats current=f window=3 last(total_received) as recv_lag3
| streamstats current=f window=4 last(total_received) as recv_lag4
| streamstats current=f window=5 last(total_received) as recv_lag5

| eval latency_change=avg_latency-latency_lag1
| eval sent_change=total_sent-sent_lag1
| eval recv_change=total_received-recv_lag1

| apply final_refined_502_regressor
| rename predicted(label) as forecast_log_count

| eval forecasted_502_count=round(exp(forecast_log_count)-1,0)
| eval forecasted_502_count=if(forecasted_502_count<0,0,forecasted_502_count)

| eval forecast_time=_time, verify_time=_time+300

| join type=left verify_time [
    search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.timeStamp output=timeStamp
    | eval verify_time=strptime(timeStamp,"%Y-%m-%dT%H:%M:%S")
    | eval httpStatus=tonumber(httpStatus)
    | where httpStatus=502
    | bin verify_time span=1m
    | stats count as actual_502_count by verify_time]

| eval forecast_time_est=strftime(forecast_time,"%Y-%m-%d %I:%M:%S %p EST")
| eval verify_time_est=strftime(verify_time,"%Y-%m-%d %I:%M:%S %p EST")

| table forecast_time_est,verify_time_est,forecasted_502_count,actual_502_count

| sort - forecasted_502_count forecast_time desc