import os
import json
import time
import boto3
import botocore

ssm = boto3.client("ssm")

TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def wait_for_invocation(command_id: str, instance_id: str, timeout_seconds: int = 300, poll_seconds: int = 2):
    """Wait until GetCommandInvocation exists (handles InvocationDoesNotExist eventual consistency)."""
    deadline = time.time() + timeout_seconds
    last_err = None

    while time.time() < deadline:
        try:
            return ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except botocore.exceptions.ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            # This is the key fix for your screenshot error
            if code == "InvocationDoesNotExist":
                last_err = e
                time.sleep(poll_seconds)
                continue
            raise

    raise TimeoutError(f"Timed out waiting for invocation to exist. command_id={command_id} instance_id={instance_id} last_err={last_err}")

def wait_until_done(command_id: str, instance_id: str, timeout_seconds: int = 600, poll_seconds: int = 3):
    """Poll until command reaches a terminal state and return the final invocation."""
    deadline = time.time() + timeout_seconds

    inv = wait_for_invocation(command_id, instance_id, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)

    while time.time() < deadline:
        status = inv.get("Status")
        if status in TERMINAL:
            return inv
        time.sleep(poll_seconds)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

    raise TimeoutError(f"Timed out waiting for command completion. command_id={command_id} instance_id={instance_id}")

def lambda_handler(event, context):
    """
    Expected EventBridge event:
      event.detail.instanceId  (required unless DEFAULT_INSTANCE_ID set)
      event.detail.runAsUser   (optional; fallback DEFAULT_RUN_AS_USER)
      event.detail.command     (required)

    Recommended command (trigger + proof):
      bash -lc 'JOB="..."; sendevent -E FORCE_STARTJOB -J "$JOB"; sleep 5; autostatus -J "$JOB" || true; autorep -J "$JOB" -q || true'
    """
    print("EVENT:", json.dumps(event))

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    command = detail.get("command")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId (set detail.instanceId or DEFAULT_INSTANCE_ID env var)."}
    if not command:
        return {"ok": False, "error": "Missing command (set detail.command)."}

    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")

    # Send the SSM command
    try:
        resp = ssm.send_command(
            DocumentName=document_name,
            InstanceIds=[instance_id],
            Parameters={
                "command": [command],
                "runAsUser": [run_as_user],
            },
            Comment=f"Autosys trigger via {document_name}",
            # Optional but useful: SSM output to CloudWatch Logs
            CloudWatchOutputConfig={
                "CloudWatchOutputEnabled": True,
                "CloudWatchLogGroupName": "/ssm/autosys-trigger"
            }
        )
    except botocore.exceptions.ClientError as e:
        print("send_command ERROR:", str(e))
        return {"ok": False, "error": "send_command failed", "details": str(e)}

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    # Wait for completion and return logs
    try:
        inv = wait_until_done(command_id, instance_id, timeout_seconds=600, poll_seconds=3)
    except Exception as e:
        print("wait_until_done ERROR:", str(e))
        return {
            "ok": False,
            "error": "Failed waiting for SSM completion",
            "commandId": command_id,
            "instanceId": instance_id,
            "details": str(e)
        }

    status = inv.get("Status")
    stdout = inv.get("StandardOutputContent", "")
    stderr = inv.get("StandardErrorContent", "")

    return {
        "ok": status == "Success",
        "status": status,
        "instanceId": instance_id,
        "documentName": document_name,
        "runAsUser": run_as_user,
        "commandId": command_id,
        "stdout": stdout,
        "stderr": stderr,
        "cloudwatchLogGroup": "/ssm/autosys-trigger"
    }