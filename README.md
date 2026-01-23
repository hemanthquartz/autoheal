Request ID: @{triggerBody()?['request_id']}
Requested by: @{triggerBody()?['requested_by']}
Approver: @{triggerBody()?['approver_email']}

Details:
@{triggerBody()?['details']}