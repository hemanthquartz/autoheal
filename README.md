| search index=your_index sourcetype=your_sourcetype earliest=-15m latest=now
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| sort _time
| fillnull value=0 serverResponseLatency sentBytes receivedBytes

| streamstats current=f window=1 last(serverResponseLatency) as serverResponseLatency_lag1
| streamstats current=f window=2 last(serverResponseLatency) as serverResponseLatency_lag2
| streamstats current=f window=3 last(serverResponseLatency) as serverResponseLatency_lag3

| streamstats current=f window=1 last(sentBytes) as sentBytes_lag1
| streamstats current=f window=2 last(sentBytes) as sentBytes_lag2
| streamstats current=f window=3 last(sentBytes) as sentBytes_lag3

| streamstats current=f window=1 last(receivedBytes) as receivedBytes_lag1
| streamstats current=f window=2 last(receivedBytes) as receivedBytes_lag2
| streamstats current=f window=3 last(receivedBytes) as receivedBytes_lag3

| streamstats window=3 avg(serverResponseLatency) as latency_moving_avg
| streamstats window=3 avg(sentBytes) as sent_moving_avg
| streamstats window=3 avg(receivedBytes) as received_moving_avg

| eval latency_to_sent_ratio = serverResponseLatency / (sentBytes + 1)
| eval received_to_sent_ratio = receivedBytes / (sentBytes + 1)
| eval latency_change = serverResponseLatency - serverResponseLatency_lag1

| apply forecast_502_model

| eval forecasted_code = if('predicted(label)'=1, 502, null())
| eval forecast_time_utc = _time
| eval forecast_time_est = strftime(_time - 18000, "%Y-%m-%d %H:%M:%S")   /* UTC - 5h = EST */
| eval actual_time_utc = _time + 300
| eval actual_time_est = strftime(actual_time_utc - 18000, "%Y-%m-%d %H:%M:%S")

| fields forecast_time_est actual_time_est forecasted_code
| where isnotnull(forecasted_code)

| append [
    | search index=your_index sourcetype=your_sourcetype earliest=-10m latest=now
    | eval actual_time_utc = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval actual_time_est = strftime(actual_time_utc - 18000, "%Y-%m-%d %H:%M:%S")
    | eval actual_httpStatus = if(httpStatus=502, 502, null())
    | table actual_time_est actual_httpStatus
]

| stats values(forecasted_code) as forecasted_code values(actual_httpStatus) as actual_httpStatus by actual_time_est
| rename actual_time_est as actual_time
| table forecast_time_est actual_time forecasted_code actual_httpStatus
| sort forecast_time_est