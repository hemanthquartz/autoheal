index=* sourcetype="mscs:azure:eventhub" source="*/network;"
| spath path=body.properties.httpStatus output=httpStatus
| eval timestamp=_time
| eval hour=strftime(_time, "%H") 
| eval day_of_week=strftime(_time, "%A")
| eval is_weekend=if(day_of_week=="Saturday" OR day_of_week=="Sunday", 1, 0)
| eval minute=strftime(_time, "%M")
| bin _time span=5s
| stats count as error_count by _time, hour, day_of_week, is_weekend, source, client_ip
| eval error_last_5s=lag(error_count, 1)
| eval error_last_1min=streamstats sum(error_count) window=12
| fillnull value=0
| table _time, hour, day_of_week, is_weekend, source, client_ip, error_count, error_last_5s, error_last_1min
| outputcsv 500_errors_training.csv
