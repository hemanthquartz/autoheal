curl.exe https://http-inputs-optuminsight.splunkcloud.com/services/collector/event `
  -H "Authorization: Splunk 001c0976-bf62-4f33-8b78-572e7bale966" `
  -H "Content-Type: application/json" `
  -d "{\"index\":\"oi_test\",\"event\":\"Hello, world!\",\"sourcetype\":\"manual\"}"