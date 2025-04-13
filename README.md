index=<your_index> sourcetype=<your_sourcetype>
spath path=body.properties.requestPath output=path
spath path=body.properties.clientRequestId output=clientRequestId
spath path=body.properties.serverResponseLatency output=serverResponseLatency
spath path=body.properties.clientIp output=clientIp
spath path=body.properties.requestBytes output=requestBytes
spath path=body.properties.responseBytes output=responseBytes
spath path=body.properties.activityId output=activityId
spath path=body.ruleName output=ruleName
spath path=body.backendPoolName output=backendPoolName
spath path=body.timestamp output=timestamp
eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval httpStatus = tonumber(httpStatus)
| stats count(eval(httpStatus==502)) as error_502_count,
        avg(serverResponseLatency) as avg_latency,
        sum(requestBytes) as total_sent,
        sum(responseBytes) as total_received
        by _time
| sort _time

| streamstats window=5 current=false
    last(error_502_count) as lag_1,
    last(error_502_count,2) as lag_2,
    last(error_502_count,3) as lag_3,
    last(error_502_count,4) as lag_4,
    last(error_502_count,5) as lag_5,
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
| eval alpha_10 = 2 / (10 + 1)
| eval alpha_20 = 2 / (20 + 1)
| streamstats window=1
    eval(alpha_10 * error_502_count + (1 - alpha_10) * exp_moving_avg_10) as exp_moving_avg_10,
    eval(alpha_20 * error_502_count + (1 - alpha_20) * exp_moving_avg_20) as exp_moving_avg_20

| fillnull value=0 rolling_mean_10 rolling_mean_20 rolling_std_10 rolling_std_20 exp_moving_avg_10 exp_moving_avg_20

| where isnotnull(error_502_count) AND error_502_count > 0

| streamstats count as row_num
| eventstats max(row_num) as total_rows
| eval train_cutoff=round(total_rows * 0.8)
| eval data_type=if(row_num <= train_cutoff, "train", "forecast")

| fit GradientBoostingRegressor error_502_count from
    lag_1, lag_2, lag_3, lag_4, lag_5,
    rolling_mean_10, rolling_mean_20,
    rolling_std_10, rolling_std_20,
    exp_moving_avg_10, exp_moving_avg_20
    into "gb_forecast_model" when data_type="train"

| apply "gb_forecast_model" as gb_prediction into data_type="forecast"

| where data_type="forecast"
| table _time gb_prediction
