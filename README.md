| inputlookup pdeObservability_all.csv
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

| movingavg serverResponseLatency as latency_moving_avg window=3
| movingavg sentBytes as sent_moving_avg window=3
| movingavg receivedBytes as received_moving_avg window=3

| eval latency_to_sent_ratio = serverResponseLatency / (sentBytes + 1)
| eval received_to_sent_ratio = receivedBytes / (sentBytes + 1)
| eval latency_change = serverResponseLatency - serverResponseLatency_lag1

| eval is_502_error = if(httpStatus=502, 1, 0)

| streamstats current=f window=5 max(is_502_error) as future_5m_is_502
| streamstats current=f window=10 max(is_502_error) as future_10m_is_502

| eval label = if(future_5m_is_502=1 OR future_10m_is_502=1, 1, 0)

| fields _time serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3 sentBytes_lag1 sentBytes_lag2 sentBytes_lag3 receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3 latency_moving_avg sent_moving_avg received_moving_avg latency_to_sent_ratio received_to_sent_ratio latency_change label

| fit GBTClassifier label from 
    serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3
    sentBytes_lag1 sentBytes_lag2 sentBytes_lag3
    receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3
    latency_moving_avg sent_moving_avg received_moving_avg
    latency_to_sent_ratio received_to_sent_ratio latency_change
    into forecast_502_model





| inputlookup pdeObservability_all.csv
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

| movingavg serverResponseLatency as latency_moving_avg window=3
| movingavg sentBytes as sent_moving_avg window=3
| movingavg receivedBytes as received_moving_avg window=3

| eval latency_to_sent_ratio = serverResponseLatency / (sentBytes + 1)
| eval received_to_sent_ratio = receivedBytes / (sentBytes + 1)
| eval latency_change = serverResponseLatency - serverResponseLatency_lag1

| apply forecast_502_model

| eval forecasted_code = if('predicted(label)'=1, 502, null())
| eval forecast_time = _time
| eval actual_time = _time + 300

| fields forecast_time actual_time forecasted_code
| where isnotnull(forecasted_code)

| append [
    | inputlookup pdeObservability_all.csv
    | eval actual_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | eval actual_httpStatus = if(httpStatus=502, 502, null())
    | table actual_time actual_httpStatus
]

| stats values(forecasted_code) as forecasted_code values(actual_httpStatus) as actual_httpStatus by actual_time
| eval forecast_time = actual_time - 300
| table forecast_time actual_time forecasted_code actual_httpStatus
| sort forecast_time
