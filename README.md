import os, json, time, re
import boto3
import botocore

ssm = boto3.client("ssm")
TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def wait_for_invocation(command_id, instance_id, timeout_seconds=300):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            return ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except botocore.exceptions.ClientError as e:
            if e.response.get("Error", {}).get("Code") == "InvocationDoesNotExist":
                time.sleep(2)
                continue
            raise
    raise TimeoutError("Invocation never appeared")

def wait_until_done(command_id, instance_id, timeout_seconds=900):
    inv = wait_for_invocation(command_id, instance_id, timeout_seconds)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if inv.get("Status") in TERMINAL:
            return inv
        time.sleep(3)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    raise TimeoutError("SSM command did not finish in time")

def extract_autosys_status(stdout: str) -> str:
    # Pull the part between AUTOSTATUS polls and AUTOREP (based on the command I gave)
    if not stdout:
        return ""
    m = re.search(r"(----- POLL 1 -----.*?)(===== AUTOREP SUMMARY =====|$)", stdout, re.S | re.I)
    if m:
        return m.group(1).strip()
    # fallback: return full stdout
    return stdout.strip()

def lambda_handler(event, context):
    detail = event.get("detail") or {}
    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    command = detail.get("command")
    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")

    if not instance_id or not command:
        return {"ok": False, "error": "Missing instanceId or command"}

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={"command": [command], "runAsUser": [run_as_user]},
        Comment="Autosys trigger + status"
    )

    command_id = resp["Command"]["CommandId"]

    # We wait only so we can collect stdout (which contains Autosys job status)
    inv = wait_until_done(command_id, instance_id, timeout_seconds=900)

    stdout = inv.get("StandardOutputContent", "")
    stderr = inv.get("StandardErrorContent", "")

    autosys_status = extract_autosys_status(stdout)

    return {
        "ok": True,
        "job": detail.get("jobName", ""),   # optional if you pass it
        "autosysStatus": autosys_status,
        "autosysRawStdout": stdout,         # keep for debugging
        "autosysStderr": stderr
    }