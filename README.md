| index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath input=body.path httpStatus output=httpStatus
| spath input=body path=body.properties.serverResponseLatency output=latency
| spath input=body path=body.backendResponseCode output=backendCode
| spath input=body path=body.properties.clientIP output=clientIP
| spath input=body path=body.timeStamp output=timeStamp
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S%z")
| eval is_500_error = if(httpStatus>=500 AND httpStatus<600, 1, 0)
| timechart span=5m sum(is_500_error) as error_500_count
| fillnull value=0 error_500_count

| streamstats current=f window=1 last(error_500_count) as lag_1
| streamstats current=f window=2 last(error_500_count) as lag_2
| streamstats current=f window=3 last(error_500_count) as lag_3
| streamstats current=f window=4 last(error_500_count) as lag_4
| streamstats current=f window=5 last(error_500_count) as lag_5
| streamstats current=f window=6 last(error_500_count) as lag_6
| streamstats current=f window=7 last(error_500_count) as lag_7
| streamstats current=f window=8 last(error_500_count) as lag_8
| eval avg_3 = (lag_1 + lag_2 + lag_3)/3
| eval avg_5 = (lag_1 + lag_2 + lag_3 + lag_4 + lag_5)/5
| eval volatility = stdev(lag_1, lag_2, lag_3, lag_4, lag_5)
| eval trend = if(lag_1 > lag_2 AND lag_2 > lag_3, 1, 0)
| eval target = error_500_count
| fields _time target lag_1 lag_2 lag_3 lag_4 lag_5 avg_3 avg_5 volatility trend

| eventstats count as total_rows
| streamstats count as row_num
| eval split = round(total_rows * 0.8)
| eval is_train = if(row_num <= split, 1, 0)

| eval model_features = "lag_1, lag_2, lag_3, lag_4, lag_5, avg_3, avg_5, volatility, trend"

| where is_train=1
| fit RandomForestRegressor target from lag_1, lag_2, lag_3, lag_4, lag_5, avg_3, avg_5, volatility, trend into http_500_forecaster
| where is_train=0
| apply http_500_forecaster as forecasted
| eval accuracy = round(100 - abs((forecasted - target) / (target + 0.01)) * 100, 2)
| eval accuracy = if(accuracy < 0 OR isnull(accuracy), 0, accuracy)
| table _time target forecasted accuracy
