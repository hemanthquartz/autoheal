| inputlookup historical_data.csv
| eval timestamp_epoch = strptime(timestamp, "%Y-%m-%d %H:%M:%S")
| bin timestamp_epoch span=5m  # Aggregate data by 5-minute intervals
| stats count(eval(httpStatus=500)) as error_count by timestamp_epoch
| eval lag_1 = mvindex(error_count, -1)
| eval lag_2 = mvindex(error_count, -2)
| eval lag_3 = mvindex(error_count, -3)
| eval lag_4 = mvindex(error_count, -4)
| eval lag_5 = mvindex(error_count, -5)
| eval target = error_count  # What we want to forecast
| table timestamp_epoch, target, lag_1, lag_2, lag_3, lag_4, lag_5
| fit RandomForestRegressor target from lag_1, lag_2, lag_3, lag_4, lag_5 into httpsstatusforecaster



| inputlookup recent_data.csv
| eval timestamp_epoch = strptime(timestamp, "%Y-%m-%d %H:%M:%S")
| bin timestamp_epoch span=5m
| stats count(eval(httpStatus=500)) as error_count by timestamp_epoch
| eval lag_1 = mvindex(error_count, -1)
| eval lag_2 = mvindex(error_count, -2)
| eval lag_3 = mvindex(error_count, -3)
| eval lag_4 = mvindex(error_count, -4)
| eval lag_5 = mvindex(error_count, -5)
| apply httpsstatusforecaster
| table timestamp_epoch, predicted(target)


index=* sourcetype="mscs:azure:eventhub" source="*/network:*"
| spath path=body.properties.httpStatus output=httpStatus
| spath path=body.properties.clientIP output=clientIP
| spath path=body.timeStamp output=timeStamp
| spath path=body.properties.serverResponseLatency output=serverResponseLatency
| spath path=body.properties.sentBytes output=sentBytes
| spath path=body.properties.receivedBytes output=receivedBytes
| spath path=body.properties.error_info output=error_info
| spath path=body.properties.sslcipher output=sslcipher
| spath path=body.properties.transactionId output=transactionId
| spath path=body.properties.serverRouted output=serverRouted
| spath path=body.properties.ruleName output=ruleName
| spath path=body.properties.operationName output=operationName
| spath path=body.properties.backendPoolName output=backendPoolName
| spath path=body.timeStamp output=timeStamp
| eval _time=strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| bin _time span=5m

| stats count(eval(httpStatus=500)) as error_count,
        avg(serverResponseLatency) as avg_latency,
        sum(sentBytes) as total_sent,
        sum(receivedBytes) as total_received
        by _time

| sort _time
| streamstats window=5 current=false last(error_count) as lag_1,
                                   last(error_count) as lag_2,
                                   last(error_count) as lag_3,
                                   last(error_count) as lag_4,
                                   last(error_count) as lag_5
| where isnotnull(lag_5)

| eval target = error_count

| fit RandomForestRegressor target from lag_1, lag_2, lag_3, lag_4, lag_5 into hsf

| apply hsf as predicted_error_count

| eval predicted_error_count = round(predicted_error_count, 0)
| eval predicted_status = if(predicted_error_count > 500, "502", "200")

| table _time, error_count, predicted_error_count, predicted_status, lag_1, lag_2, lag_3, lag_4, lag_5

