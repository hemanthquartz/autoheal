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
