index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath input=body.httpStatus output=httpStatus
| spath input=body.clientIP output=clientIP
| spath input=body.httpMethod output=httpMethod
| spath input=body.userAgent output=userAgent
| spath input=body.backendPoolName output=backendPoolName
| spath input=body.timeStamp output=timestamp
| eval _time = strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
| eval is_5xx = if(httpStatus >= 500 AND httpStatus < 600, 1, 0)
| eval hour = strftime(_time, "%H"), day = strftime(_time, "%A")
| table _time, is_5xx, httpMethod, userAgent, backendPoolName, hour, day
| sort _time
| streamstats count as row_number
| eventstats max(row_number) as total_rows
| eval split_point = round(total_rows * 0.8)
| eval dataset = if(row_number <= split_point, "train", "forecast")
| eval label = is_5xx

| eval httpMethod=coalesce(httpMethod, "unknown"), userAgent=coalesce(userAgent, "unknown"), backendPoolName=coalesce(backendPoolName, "unknown"), hour=coalesce(hour, "0"), day=coalesce(day, "unknown")

| fit RandomForestClassifier label from httpMethod, userAgent, backendPoolName, hour, day into http_error_forecast_model when dataset="train"
| apply http_error_forecast_model when dataset="forecast"

| eval match = if(label == 'predicted(label)', 1, 0)
| eventstats count as total_forecast
| stats count(eval(match=1)) as correct count as total
| eval accuracy = round((correct / total) * 100, 2)
| fields accuracy, correct, total
| appendpipe [
    | search dataset="forecast"
    | confusionmatrix label predicted(label)
]