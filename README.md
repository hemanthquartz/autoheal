import os, json, time
import boto3

ssm = boto3.client("ssm")

TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    detail = event.get("detail") or {}
    instance_id = detail["instanceId"]
    run_as_user = detail.get("runAsUser", os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user"))
    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")

    # IMPORTANT: send a command that includes verification output
    command = detail["command"]  # send the wrapped command shown above

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [command],
            "runAsUser": [run_as_user],
        },
        Comment=f"Autosys trigger via {document_name}",
        CloudWatchOutputConfig={
            "CloudWatchOutputEnabled": True,
            "CloudWatchLogGroupName": "/ssm/autosys-trigger"
        }
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    # wait for completion
    deadline = time.time() + 300  # 5 minutes
    while time.time() < deadline:
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        status = inv.get("Status")
        if status in TERMINAL:
            return {
                "ok": status == "Success",
                "status": status,
                "instanceId": instance_id,
                "documentName": document_name,
                "runAsUser": run_as_user,
                "commandId": command_id,
                "stdout": inv.get("StandardOutputContent", ""),
                "stderr": inv.get("StandardErrorContent", ""),
                "cloudwatchLogGroup": "/ssm/autosys-trigger"
            }
        time.sleep(3)

    return {
        "ok": False,
        "status": "TimeoutWaitingForSSM",
        "instanceId": instance_id,
        "commandId": command_id
    }