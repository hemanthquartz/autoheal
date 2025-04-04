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