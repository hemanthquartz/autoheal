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

| fillnull value=0 *

| eventstats count as total_rows
| streamstats count as row_number
| eval mode=if(row_number <= total_rows * 0.8, "train", "forecast")
| eval target=if(mode="train", error_502_count, null())

| fit GradientBoostingRegressor target from 
    avg_latency, total_sent, total_received,
    lag_1, lag_2, lag_3, lag_4, lag_5,
    rolling_mean_10, rolling_std_10,
    latency_x_sent, latency_x_received, sent_minus_received,
    minute, hour, dayofweek
    into "mltk_forecast_model_502"

| where mode="forecast"
| apply "mltk_forecast_model_502"
| rename predicted as forecast_502
| eval error = abs(forecast_502 - error_502_count)
| eval squared_error = pow(forecast_502 - error_502_count, 2)

| eventstats avg(error_502_count) as mean_actual
| eval ss_total = pow(error_502_count - mean_actual, 2)
| eventstats sum(squared_error) as SSE sum(ss_total) as SST
| eval r2_score = round(1 - (SSE / SST), 3)

| table _time error_502_count forecast_502 error r2_score