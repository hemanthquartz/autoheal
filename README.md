| index=* sourcetype="mscs:azure:eventhub" source="*/network"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| where httpStatus = 502

| timechart span=5m count as error_502_count avg(serverResponseLatency) as avg_latency sum(sentBytes) as total_sent sum(receivedBytes) as total_received

| streamstats window=5 current=false 
    last(error_502_count) as lag_1,
    last(error_502_count) as lag_2,
    last(error_502_count) as lag_3,
    last(error_502_count) as lag_4,
    last(error_502_count) as lag_5,
    last(avg_latency) as avg_latency_lag,
    last(total_sent) as total_sent_lag,
    last(total_received) as total_received_lag

| fillnull value=0 lag_1 lag_2 lag_3 lag_4 lag_5 avg_latency_lag total_sent_lag total_received_lag

| streamstats window=10 current=false avg(error_502_count) as rolling_mean_10
| streamstats window=20 current=false avg(error_502_count) as rolling_mean_20

| eval deviation_10 = abs(error_502_count - rolling_mean_10)
| eval deviation_20 = abs(error_502_count - rolling_mean_20)
| streamstats window=10 current=false avg(deviation_10) as rolling_std_10
| streamstats window=20 current=false avg(deviation_20) as rolling_std_20

| fillnull value=0 rolling_mean_10 rolling_mean_20 rolling_std_10 rolling_std_20

| fit RandomForestRegressor error_502_count from 
    lag_1, lag_2, lag_3, lag_4, lag_5,
    avg_latency_lag, total_sent_lag, total_received_lag,
    rolling_mean_10, rolling_mean_20, rolling_std_10, rolling_std_20
    into "rf_model_502"

| apply "rf_model_502"
| rename predicted as rf_prediction

| eval error = error_502_count - rf_prediction
| eval abs_error = abs(error)
| eval squared_error = pow(error, 2)

| eventstats avg(error_502_count) as mean_actual
| eval total_variance = pow(error_502_count - mean_actual, 2)

| eventstats sum(squared_error) as SSE, sum(total_variance) as SST, count as n
| eval r2 = 1 - (SSE / SST)
| eval rmse = sqrt(SSE / n)
| eval mae = avg(abs_error)

| table _time error_502_count rf_prediction error abs_error squared_error r2 rmse mae