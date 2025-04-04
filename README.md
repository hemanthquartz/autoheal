| inputlookup historical_data.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| fit RandomForestClassifier httpStatus from hour_of_day, day_of_week, day_of_month, clientIP, operationName, ruleName, backendPoolName, sentBytes, receivedBytes, serverResponseLatency, sslCipher, serverRooted into httpsstatuspredictor


| inputlookup recent_logs.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| apply httpsstatuspredictor
| where predicted(httpStatus)=500


| inputlookup forecast_test_data.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| apply httpsstatuspredictor
| eval prediction_status = if(predicted(httpStatus) == httpStatus, "Correct", "Incorrect")
| stats count as total, count(eval(prediction_status="Correct")) as correct, count(eval(prediction_status="Incorrect")) as incorrect
| eval accuracy = round((correct / total) * 100, 2)



| inputlookup forecast_test_data.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| apply httpsstatuspredictor
| where predicted(httpStatus) != httpStatus
| table timestamp, httpStatus, predicted(httpStatus), clientIP, operationName, ruleName, backendPoolName



| inputlookup historical_http_errors.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| timechart span=5m count(httpStatus=500) as error_count
| streamstats window=5 sum(error_count) as rolling_error_count
| eval future_error = if(rolling_error_count > 0, 1, 0)
| fit RandomForestClassifier future_error from rolling_error_count, hour_of_day, day_of_week, day_of_month into future_error_predictor



| inputlookup recent_http_logs.csv
| eval hour_of_day = strftime(timestamp, "%H")
| eval day_of_week = strftime(timestamp, "%A")
| eval day_of_month = strftime(timestamp, "%d")
| timechart span=5m count(httpStatus=500) as error_count
| streamstats window=5 sum(error_count) as rolling_error_count
| apply future_error_predictor
| where predicted(future_error) = 1

