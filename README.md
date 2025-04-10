| index=* sourcetype="mscs:azure:eventhub" source="*/network"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| where httpStatus = 502

| timechart span=5m count as error_502_count avg(serverResponseLatency) as avg_latency sum(sentBytes) as total_sent sum(receivedBytes) as total_received

| eval latency_x_sent = avg_latency * total_sent
| eval latency_x_received = avg_latency * total_received
| eval sent_minus_received = total_sent - total_received

| streamstats window=5 current=false 
    last(avg_latency) as lag_1,
    last(avg_latency, 2) as lag_2,
    last(avg_latency, 3) as lag_3,
    last(avg_latency, 4) as lag_4,
    last(avg_latency, 5) as lag_5

| streamstats window=10 current=false 
    avg(avg_latency) as rolling_mean_10,
    stdev(avg_latency) as rolling_std_10

| eval minute = tonumber(strftime(_time, "%M"))
| eval hour = tonumber(strftime(_time, "%H"))
| eval dayofweek = tonumber(strftime(_time, "%w"))

| fillnull value=0 lag_1 lag_2 lag_3 lag_4 lag_5 rolling_mean_10 rolling_std_10 latency_x_sent latency_x_received sent_minus_received

| eval is_training = if(_time < relative_time(now(), "-50m"), 1, 0)

| eval model_input_features = mvappend(
    avg_latency, total_sent, total_received,
    lag_1, lag_2, lag_3, lag_4, lag_5,
    rolling_mean_10, rolling_std_10,
    latency_x_sent, latency_x_received, sent_minus_received,
    minute, hour, dayofweek
)

| where is_training=1
| fit RandomForestRegressor error_502_count from 
    avg_latency, total_sent, total_received,
    lag_1, lag_2, lag_3, lag_4, lag_5,
    rolling_mean_10, rolling_std_10,
    latency_x_sent, latency_x_received, sent_minus_received,
    minute, hour, dayofweek
    into "rf_forecast_model_502"

| fit GradientBoostingRegressor error_502_count from 
    avg_latency, total_sent, total_received,
    lag_1, lag_2, lag_3, lag_4, lag_5,
    rolling_mean_10, rolling_std_10,
    latency_x_sent, latency_x_received, sent_minus_received,
    minute, hour, dayofweek
    into "gb_forecast_model_502"

| append [
    | index=* sourcetype="mscs:azure:eventhub" source="*/network"
    | spath path=body.properties.httpStatus output=httpStatus
    | spath path=body.properties.serverResponseLatency output=serverResponseLatency
    | spath path=body.properties.sentBytes output=sentBytes
    | spath path=body.properties.receivedBytes output=receivedBytes
    | spath path=body.timeStamp output=timeStamp
    | eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
    | where httpStatus = 502 AND _time >= relative_time(now(), "-50m")
    
    | timechart span=5m count as error_502_count avg(serverResponseLatency) as avg_latency sum(sentBytes) as total_sent sum(receivedBytes) as total_received
    
    | eval latency_x_sent = avg_latency * total_sent
    | eval latency_x_received = avg_latency * total_received
    | eval sent_minus_received = total_sent - total_received
    
    | streamstats window=5 current=false 
        last(avg_latency) as lag_1,
        last(avg_latency, 2) as lag_2,
        last(avg_latency, 3) as lag_3,
        last(avg_latency, 4) as lag_4,
        last(avg_latency, 5) as lag_5

    | streamstats window=10 current=false 
        avg(avg_latency) as rolling_mean_10,
        stdev(avg_latency) as rolling_std_10

    | eval minute = tonumber(strftime(_time, "%M"))
    | eval hour = tonumber(strftime(_time, "%H"))
    | eval dayofweek = tonumber(strftime(_time, "%w"))

    | fillnull value=0 lag_1 lag_2 lag_3 lag_4 lag_5 rolling_mean_10 rolling_std_10 latency_x_sent latency_x_received sent_minus_received
]

| apply "rf_forecast_model_502"
| rename predicted as rf_prediction
| apply "gb_forecast_model_502"
| rename predicted as gb_prediction

| eval predicted = round((rf_prediction + gb_prediction) / 2)
| table _time error_502_count predicted