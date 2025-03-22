index=your_index sourcetype=mscs:azure:eventhub 
| spath input=body
| table timeStamp clientIP httpStatus serverResponseLatency ruleName operationName backendPoolName sentBytes receivedBytes error_info sslCipher serverRooted transactionId
| eval timeStamp=strftime(timeStamp, "%Y-%m-%d %H:%M:%S")
| where httpStatus>=200 AND httpStatus<600
| fillnull value="N/A" ruleName backendPoolName operationName error_info sslCipher serverRooted
| fillnull value=0 serverResponseLatency sentBytes receivedBytes
