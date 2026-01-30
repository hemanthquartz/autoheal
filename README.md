import os
import json
import time
import boto3
import botocore

ssm = boto3.client("ssm")

TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def _client_error_code(e: Exception) -> str:
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response.get("Error", {}).get("Code", "")
    return ""

def wait_for_invocation(command_id: str, instance_id: str, timeout_seconds: int = 300, poll_seconds: int = 2):
    """SSM is eventually consistent; invocation may not exist immediately."""
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        try:
            return ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except botocore.exceptions.ClientError as e:
            last = e
            if _client_error_code(e) == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise
    raise TimeoutError(f"Timed out waiting for invocation to exist. {command_id=} {instance_id=} last={last}")

def wait_until_done(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    """Poll until terminal status so we can capture stdout/stderr (Autosys output)."""
    deadline = time.time() + timeout_seconds
    inv = wait_for_invocation(command_id, instance_id, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)

    while time.time() < deadline:
        status = inv.get("Status")
        if status in TERMINAL:
            return inv
        time.sleep(poll_seconds)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

    raise TimeoutError(f"Timed out waiting for command completion. {command_id=} {instance_id=}")

def build_autosys_proof_command(job_name: str) -> str:
    """
    Build a command that:
      - prints PATH checks (so we see if autosys commands exist)
      - triggers the job
      - prints autostatus + autorep output (proof)
    Output is forced into stdout via 2>&1 so Lambda can return it.
    """
    # Use single quotes around the job name to avoid breaking the SSM doc's bash -c quoting.
    j = job_name.replace("'", "'\"'\"'")  # safe quote for single-quote context
    return (
        "echo '=== CONTEXT ===' ; "
        "date -Is 2>&1 ; whoami 2>&1 ; hostname 2>&1 ; "
        "echo \"PWD=$(pwd)\" 2>&1 ; "
        "echo '=== CHECK AUTOSYS BINARIES ===' ; "
        "command -v sendevent 2>&1 || echo 'MISSING: sendevent' ; "
        "command -v autostatus 2>&1 || echo 'MISSING: autostatus' ; "
        "command -v autorep 2>&1 || echo 'MISSING: autorep' ; "
        "echo '=== TRIGGER ===' ; "
        f"sendevent -E FORCE_STARTJOB -J '{j}' 2>&1 ; "
        "echo 'Sleeping 10s...' 2>&1 ; "
        "sleep 10 ; "
        "echo '=== AUTOSTATUS ===' ; "
        f"autostatus -J '{j}' 2>&1 ; "
        "echo '=== AUTOREP (summary) ===' ; "
        f"autorep -J '{j}' -q 2>&1 ; "
        "echo '=== DONE ===' ; date -Is 2>&1"
    )

def lambda_handler(event, context):
    """
    Event expected (EventBridge or direct test):
      {
        "detail": {
          "instanceId": "i-xxxx",
          "runAsUser": "bk6dev1",
          "jobName": "GV7#ECM#box#ECM_GL_VEND_ADHOC_DEVL1"
        }
      }

    You can also pass detail.command if you want to override what runs.
    If detail.command is NOT passed, we auto-build a command that prints Autosys status.
    """
    print("EVENT:", json.dumps(event))

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    job_name = detail.get("jobName") or os.environ.get("DEFAULT_AUTOSYS_JOB", "")
    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId (detail.instanceId or DEFAULT_INSTANCE_ID env var)"}

    # Either use caller-provided command, or build a proof command from jobName
    command = detail.get("command")
    if not command:
        if not job_name:
            return {
                "ok": False,
                "error": "Missing command and jobName. Provide detail.command or detail.jobName (or DEFAULT_AUTOSYS_JOB env var)."
            }
        command = build_autosys_proof_command(job_name)

    # CloudWatch log group for SSM output (optional)
    cw_log_group = os.environ.get("SSM_CW_LOG_GROUP", "/ssm/autosys-trigger")

    # 1) Send SSM command
    try:
        resp = ssm.send_command(
            DocumentName=document_name,
            InstanceIds=[instance_id],
            Parameters={
                "command": [command],
                "runAsUser": [run_as_user],
            },
            Comment=f"Autosys trigger + status via {document_name}",
            CloudWatchOutputConfig={
                "CloudWatchOutputEnabled": True,
                "CloudWatchLogGroupName": cw_log_group
            }
        )
    except botocore.exceptions.ClientError as e:
        return {"ok": False, "error": "send_command failed", "details": str(e)}

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    # 2) Wait until the command finishes so we can collect stdout/stderr (which contains Autosys status)
    try:
        inv = wait_until_done(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    except Exception as e:
        return {
            "ok": False,
            "error": "Failed waiting for SSM completion",
            "commandId": command_id,
            "instanceId": instance_id,
            "cloudwatchLogGroup": cw_log_group,
            "details": str(e)
        }

    stdout = inv.get("StandardOutputContent", "") or ""
    stderr = inv.get("StandardErrorContent", "") or ""

    # 3) Return Autosys job status evidence (from stdout)
    # We return full stdout because it includes autostatus/autorep output now.
    return {
        "ok": inv.get("Status") == "Success",
        "instanceId": instance_id,
        "runAsUser": run_as_user,
        "documentName": document_name,
        "commandId": command_id,
        "jobName": job_name,
        "autosysOutput": stdout.strip(),
        "autosysError": stderr.strip(),
        "cloudwatchLogGroup": cw_log_group
    }