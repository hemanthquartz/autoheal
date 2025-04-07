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
| eval _time = strptime(timeStamp, "%Y-%m-%dT%H:%M:%S")
| where httpStatus = 502 OR httpStatus = 503

| stats count(eval(httpStatus=502)) as error_502_count, 
        count(eval(httpStatus=503)) as error_503_count,
        avg(serverResponseLatency) as avg_latency,
        sum(sentBytes) as total_sent,
        sum(receivedBytes) as total_received
        by _time

| streamstats window=5 current=false last(error_502_count) as lag_1,
                                   last(error_502_count) as lag_2,
                                   last(error_502_count) as lag_3,
                                   last(error_502_count) as lag_4,
                                   last(error_502_count) as lag_5,
                                   last(avg_latency) as avg_latency_lag,
                                   last(total_sent) as total_sent_lag,
                                   last(total_received) as total_received_lag,
                                   last(error_503_count) as error_503_lag

| fillnull value=0 lag_1 lag_2 lag_3 lag_4 lag_5 avg_latency_lag total_sent_lag total_received_lag error_503_lag

| fit RandomForestRegressor "error_502_count" from 
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_5", 
    "avg_latency_lag", "total_sent_lag", "total_received_lag", "error_503_lag"
    into "rf_forecast_model_502"

| fit GradientBoostingRegressor "error_502_count" from 
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_5", 
    "avg_latency_lag", "total_sent_lag", "total_received_lag", "error_503_lag"
    into "gb_forecast_model_502"