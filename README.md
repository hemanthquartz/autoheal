| makeresults count=10
| streamstats count as future_index
| eval _time = now() + (future_index * 300)
| eval lag_1=0, lag_2=0, lag_3=0, lag_4=0, lag_5=0
| eval avg_latency_lag=0, total_sent_lag=0, total_received_lag=0
| eval rolling_mean_10=0, rolling_mean_20=0, rolling_std_10=0, rolling_std_20=0
| eval exp_moving_avg_10=0, exp_moving_avg_20=0

| apply "rf_forecast_model_502"
| rename predicted as rf_prediction

| apply "gb_forecast_model_502"
| rename predicted as gb_prediction

| eval predicted = coalesce((rf_prediction + gb_prediction) / 2, rf_prediction, gb_prediction)
| table _time, predicted