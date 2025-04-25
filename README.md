index=<your_index> earliest=-1d@d latest=@d
| timechart span=1m count(eval(httpStatus==502)) AS error_count
| autoregress error_count p=1-5
| reverse
| autoregress error_count p=10
| reverse
| rename error_count_p10 AS error_count_future
| where isnotnull(error_count_future) AND isnotnull(error_count_p5)
| fit RandomForestRegressor error_count_future from error_count error_count_p1 error_count_p2 error_count_p3 error_count_p4 error_count_p5 n_estimators=200 into "RF_502_model"
| fit StateSpaceForecast error_count into "SS_502_model"



index=<your_index> earliest=-30m
| timechart span=1m count(eval(httpStatus==502)) AS error_count
| autoregress error_count p=1-5
| reverse
| autoregress error_count p=10
| reverse
| rename error_count_p10 AS actual_count
| where isnotnull(actual_count) AND isnotnull(error_count_p5)
| eval current_time = _time, forecast_time = _time + 600
| apply RF_502_model
| rename "predicted(error_count_future)" AS rf_forecast
| apply SS_502_model
| rename "predicted(error_count)" AS ss_forecast
| eval forecasted_count = round((rf_forecast + ss_forecast)/2, 0)
| eval current_time = strftime(current_time, "%Y-%m-%d %H:%M:%S %Z")
| eval forecast_time = strftime(forecast_time, "%Y-%m-%d %H:%M:%S %Z")
| table forecasted_count actual_count current_time forecast_time
