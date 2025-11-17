"pass_state": {
  "Type": "Pass",
  "ResultSelector": {
    "eventType.$": "$.eventType",
    "messageId.$": "$.messageId",
    "Inbound_Bucket.$": "$.Inbound_Bucket",
    "Inbound_Key.$": "$.Inbound_Key",
    "s3path.$": "$.s3path",
    "archive.$": "$.archive"
  },
  "ResultPath": "$",
  "End": true
}