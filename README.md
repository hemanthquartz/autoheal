index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-1d
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| bin _time span=1m
| stats avg(serverResponseLatency) as avg_latency, sum(sentBytes) as total_sent, sum(receivedBytes) as total_received, count(eval(httpStatus=502)) as count_502 by _time
| sort 0 _time
| streamstats window=1 last(avg_latency) as serverResponseLatency_lag1
| streamstats window=2 last(avg_latency) as serverResponseLatency_lag2
| streamstats window=3 last(avg_latency) as serverResponseLatency_lag3
| streamstats window=1 last(total_sent) as sentBytes_lag1
| streamstats window=2 last(total_sent) as sentBytes_lag2
| streamstats window=3 last(total_sent) as sentBytes_lag3
| streamstats window=1 last(total_received) as receivedBytes_lag1
| streamstats window=2 last(total_received) as receivedBytes_lag2
| streamstats window=3 last(total_received) as receivedBytes_lag3
| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1
| streamstats window=5 sum(count_502) as future_5m_502_sum
| streamstats window=10 sum(count_502) as future_10m_502_sum
| eval label = if(future_5m_502_sum >= 2 OR future_10m_502_sum >= 3, 1, 0)
| eval latency_sent_diff = avg_latency - (total_sent/1000)
| eval received_sent_ratio_change = received_to_sent_ratio - latency_to_sent_ratio
| eval latency_spike = if(latency_change > 50, 1, 0)
| eval data_drop = if(total_sent < sent_moving_avg*0.5, 1, 0)
| eval stress_signal = if(latency_spike=1 AND data_drop=1, 1, 0)
| fit GradientBoostingClassifier label from serverResponseLatency_lag1 serverResponseLatency_lag2 serverResponseLatency_lag3 sentBytes_lag1 sentBytes_lag2 sentBytes_lag3 receivedBytes_lag1 receivedBytes_lag2 receivedBytes_lag3 latency_moving_avg sent_moving_avg received_moving_avg latency_to_sent_ratio received_to_sent_ratio latency_sent_diff received_sent_ratio_change latency_spike data_drop stress_signal latency_change into forecast_502_classifier_model





index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-20m
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| bin _time span=1m
| stats avg(serverResponseLatency) as avg_latency, sum(sentBytes) as total_sent, sum(receivedBytes) as total_received, count(eval(httpStatus=502)) as count_502 by _time
| sort 0 _time
| streamstats window=1 last(avg_latency) as serverResponseLatency_lag1
| streamstats window=2 last(avg_latency) as serverResponseLatency_lag2
| streamstats window=3 last(avg_latency) as serverResponseLatency_lag3
| streamstats window=1 last(total_sent) as sentBytes_lag1
| streamstats window=2 last(total_sent) as sentBytes_lag2
| streamstats window=3 last(total_sent) as sentBytes_lag3
| streamstats window=1 last(total_received) as receivedBytes_lag1
| streamstats window=2 last(total_received) as receivedBytes_lag2
| streamstats window=3 last(total_received) as receivedBytes_lag3
| streamstats window=3 avg(avg_latency) as latency_moving_avg
| streamstats window=3 avg(total_sent) as sent_moving_avg
| streamstats window=3 avg(total_received) as received_moving_avg
| eval latency_to_sent_ratio = avg_latency / (total_sent + 1)
| eval received_to_sent_ratio = total_received / (total_sent + 1)
| eval latency_change = avg_latency - serverResponseLatency_lag1
| eval latency_sent_diff = avg_latency - (total_sent/1000)
| eval received_sent_ratio_change = received_to_sent_ratio - latency_to_sent_ratio
| eval latency_spike = if(latency_change > 50, 1, 0)
| eval data_drop = if(total_sent < sent_moving_avg*0.5, 1, 0)
| eval stress_signal = if(latency_spike=1 AND data_drop=1, 1, 0)
| apply forecast_502_classifier_model
| eval future_502_risk = if('predicted(label)'=1, "DANGER", "SAFE")
| eval forecasted_502_count = if(future_502_risk="DANGER", 1, 0)
| eval forecast_time = _time
| eval actual_time = _time + 300
| join type=left actual_time
    [ search index=* sourcetype="mscs:azure:eventhub" source="*/network;" earliest=-10m
      | spath path=body.properties.httpStatus output=httpStatus
      | spath path=body.timeStamp output=timeStamp
      | eval actual_time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
      | eval httpStatus = tonumber(httpStatus)
      | where httpStatus=502
      | bin actual_time span=1m
      | stats count as actual_502_count by actual_time
    ]
| eval forecast_time_est = strftime(forecast_time, "%Y-%m-%d %I:%M:%S %p EST")
| eval actual_time_est = strftime(actual_time, "%Y-%m-%d %I:%M:%S %p EST")
| table forecast_time_est, actual_time_est, future_502_risk, forecasted_502_count, actual_502_count
| sort forecast_time desc
