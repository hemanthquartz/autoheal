| index=* sourcetype="mscs:azure:eventhub" source="*/network"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.sslcipher output=sslcipher
| spath path=body.properties.transactionId output=transactionId
| spath path=body.properties.serverRouted output=serverRouted
| spath path=body.ruleName output=ruleName
| spath path=body.operationName output=operationName
| spath path=body.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timeStamp
| where httpStatus = 502

| timechart span=5m count as error_count avg(serverResponseLatency) as avg_latency sum(sentBytes) as total_sent sum(receivedBytes) as total_received

| eval rolling_mean_3 = mvavg(error_count, 3)
| eval rolling_mean_5 = mvavg(error_count, 5)
| eval rolling_std_3 = stdev(error_count, 3)
| eval rolling_std_5 = stdev(error_count, 5)
| eval exp_moving_avg = ema(error_count, 5)

| eval lag_1 = lag(error_count, 1)
| eval lag_2 = lag(error_count, 2)
| eval lag_3 = lag(error_count, 3)
| eval lag_4 = lag(error_count, 4)
| eval lag_5 = lag(error_count, 5)

| eval rolling_skew_3 = mstats.skew(error_count, 3)
| eval rolling_kurt_3 = mstats.kurtosis(error_count, 3)
| eval rolling_skew_5 = mstats.skew(error_count, 5)
| eval rolling_kurt_5 = mstats.kurtosis(error_count, 5)

| fillnull value=0 rolling_mean_3 rolling_mean_5 rolling_std_3 rolling_std_5 exp_moving_avg lag_1 lag_2 lag_3 lag_4 lag_5 rolling_skew_3 rolling_kurt_3 rolling_skew_5 rolling_kurt_5

| fit RandomForestRegressor "error_count" from 
    "rolling_mean_3", "rolling_mean_5", "rolling_std_3", "rolling_std_5", "exp_moving_avg",
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_5",
    "rolling_skew_3", "rolling_kurt_3", "rolling_skew_5", "rolling_kurt_5", 
    "avg_latency", "total_sent", "total_received"
    into "rf_forecast_model_502"

| fit GradientBoostingRegressor "error_count" from 
    "rolling_mean_3", "rolling_mean_5", "rolling_std_3", "rolling_std_5", "exp_moving_avg",
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_5",
    "rolling_skew_3", "rolling_kurt_3", "rolling_skew_5", "rolling_kurt_5", 
    "avg_latency", "total_sent", "total_received"
    into "gb_forecast_model_502"

| apply "rf_forecast_model_502"
| apply "gb_forecast_model_502"

| eval predicted = (rf_forecast_model_502 + gb_forecast_model_502) / 2

| table _time error_count rolling_mean_3 rolling_mean_5 rolling_std_3 rolling_std_5 exp_moving_avg lag_1 lag_2 lag_3 lag_4 lag_5 rolling_skew_3 rolling_kurt_3 rolling_skew_5 rolling_kurt_5 avg_latency total_sent total_received predicted