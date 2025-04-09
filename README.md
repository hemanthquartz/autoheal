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

| fit GradientBoostingRegressor error_502_count from 
    lag_1, lag_2, lag_3, lag_4, lag_5,
    avg_latency_lag, total_sent_lag, total_received_lag,
    rolling_mean_10, rolling_mean_20, rolling_std_10, rolling_std_20
    into "gb_model_502"

| fit LinearRegression error_502_count from 
    lag_1, lag_2, lag_3, lag_4, lag_5,
    avg_latency_lag, total_sent_lag, total_received_lag,
    rolling_mean_10, rolling_mean_20, rolling_std_10, rolling_std_20
    into "lr_model_502"

| apply "rf_model_502"
| rename predicted as rf_prediction
| apply "gb_model_502"
| rename predicted as gb_prediction
| apply "lr_model_502"
| rename predicted as lr_prediction

| eval avg_prediction = (rf_prediction + gb_prediction + lr_prediction) / 3

| score r2 error_502_count against rf_prediction as r2_rf
| score rmse error_502_count against rf_prediction as rmse_rf
| score mae error_502_count against rf_prediction as mae_rf

| score r2 error_502_count against gb_prediction as r2_gb
| score rmse error_502_count against gb_prediction as rmse_gb
| score mae error_502_count against gb_prediction as mae_gb

| score r2 error_502_count against lr_prediction as r2_lr
| score rmse error_502_count against lr_prediction as rmse_lr
| score mae error_502_count against lr_prediction as mae_lr

| table _time error_502_count rf_prediction gb_prediction lr_prediction avg_prediction r2_* rmse_* mae_*