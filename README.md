{
  "eventType.$": "States.StringToJson($.Cause).eventType",
  "messageId.$": "States.StringToJson($.Cause).messageId",
  "Inbound_Bucket.$": "States.StringToJson($.Cause).Inbound_Bucket",
  "Inbound_Key.$": "States.StringToJson($.Cause).Inbound_Key",
  "s3path.$": "States.StringToJson($.Cause).s3path",
  "archive.$": "States.StringToJson($.Cause).archive"
}