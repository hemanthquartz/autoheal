import os
import json
import time
import boto3
import botocore
from datetime import datetime, date
from decimal import Decimal
import base64

ssm = boto3.client("ssm")
SSM_TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def json_safe(obj):
    """
    Recursively convert boto3 responses to JSON-serializable structures.
    Fixes datetime MarshalError.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    if isinstance(obj, set):
        return [json_safe(x) for x in obj]
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    if isinstance(obj, tuple):
        return [json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}

    # fallback: stringify unknown types
    return str(obj)

def _err_code(e: Exception) -> str:
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response.get("Error", {}).get("Code", "")
    return ""

def wait_for_invocation(command_id: str, instance_id: str, timeout_seconds: int = 300, poll_seconds: int = 2):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            return ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except botocore.exceptions.ClientError as e:
            if _err_code(e) == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise
    raise TimeoutError(f"Invocation never appeared for {command_id} on {instance_id}")

def wait_until_done(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    inv = wait_for_invocation(command_id, instance_id, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if inv.get("Status") in SSM_TERMINAL:
            return inv
        time.sleep(poll_seconds)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    raise TimeoutError(f"SSM command did not finish in time for {command_id} on {instance_id}")

def get_plugin_details(command_id: str, instance_id: str):
    """
    Returns per-plugin details (JSON-safe). This is often where the real error is.
    """
    try:
        resp = ssm.list_command_invocations(CommandId=command_id, InstanceId=instance_id, Details=True)
        resp_safe = json_safe(resp)

        invs = resp_safe.get("CommandInvocations", [])
        if not invs:
            return {"pluginDetails": [], "pluginDetailsNote": "No CommandInvocations returned"}

        inv = invs[0]
        return {
            "pluginDetails": inv.get("CommandPlugins", []),
            "requestedDateTime": inv.get("RequestedDateTime", ""),
            "standardOutputUrl": inv.get("StandardOutputUrl", ""),
            "standardErrorUrl": inv.get("StandardErrorUrl", "")
        }
    except Exception as e:
        return {"pluginDetailsError": str(e)}

def build_debug_autosys_command(job_name: str) -> str:
    """
    IMPORTANT: do NOT wrap bash -lc here because your SSM document already runs bash -c
    and sources your profile. We just emit shell statements with strong markers + 2>&1.
    """
    safe_job = job_name.replace("'", "'\"'\"'")

    cmd = f"""
echo "__AUTOSYS_DEBUG_BEGIN__"
date -Is 2>&1
echo "JOB={safe_job}" 2>&1
echo "WHOAMI=$(whoami)" 2>&1
echo "HOST=$(hostname)" 2>&1
echo "PWD=$(pwd)" 2>&1
echo "PATH=$PATH" 2>&1

echo "__CHECK_BINARIES__" 2>&1
command -v sendevent 2>&1 || echo "MISSING:sendevent" 2>&1
command -v autostatus 2>&1 || echo "MISSING:autostatus" 2>&1
command -v autorep 2>&1 || echo "MISSING:autorep" 2>&1

echo "__STEP_SENDEVENT__" 2>&1
SE_OUT=$(sendevent -E FORCE_STARTJOB -J '{safe_job}' 2>&1)
SE_RC=$?
echo "SENDEVENT_RC=$SE_RC" 2>&1
echo "SENDEVENT_OUTPUT=$SE_OUT" 2>&1

echo "__STEP_SLEEP__" 2>&1
sleep 5

echo "__STEP_AUTOSTATUS__" 2>&1
AS_OUT=$(autostatus -J '{safe_job}' 2>&1)
AS_RC=$?
echo "AUTOSTATUS_RC=$AS_RC" 2>&1
echo "AUTOSTATUS_OUTPUT=$AS_OUT" 2>&1

echo "__STEP_AUTOREP__" 2>&1
AR_OUT=$(autorep -J '{safe_job}' -q 2>&1)
AR_RC=$?
echo "AUTOREP_RC=$AR_RC" 2>&1
echo "AUTOREP_OUTPUT=$AR_OUT" 2>&1

echo "__START_CONFIRMATION_CHECK__" 2>&1
START=NO
if [ "$SE_RC" -eq 0 ]; then START=YES; fi
echo "$AS_OUT" | egrep -qi "(RUN|RUNNING|START|STARTING|ACTIVE|EXEC|EXECUTING|IN[_ ]PROGRESS|ACTIVATED)" && START=YES
echo "START_CONFIRMED=$START" 2>&1

echo "__AUTOSYS_DEBUG_END__" 2>&1
"""
    return " ".join(line.strip() for line in cmd.splitlines() if line.strip())

def extract_evidence(stdout: str):
    if not stdout:
        return []
    evidence = []
    for ln in stdout.splitlines():
        if ln.startswith(("SENDEVENT_RC=", "SENDEVENT_OUTPUT=",
                          "AUTOSTATUS_OUTPUT=", "AUTOREP_OUTPUT=",
                          "START_CONFIRMED=", "MISSING:",
                          "__AUTOSYS_DEBUG_", "__STEP_", "__CHECK_")):
            evidence.append(ln)
    return evidence[:300]

def lambda_handler(event, context):
    print("==== LAMBDA START ====")
    print("RAW EVENT:", json.dumps(json_safe(event)))

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")
    cw_log_group = os.environ.get("SSM_CW_LOG_GROUP", "/ssm/autosys-trigger")

    job_name = detail.get("jobName") or os.environ.get("DEFAULT_AUTOSYS_JOB", "")
    command_override = detail.get("command")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId (detail.instanceId or DEFAULT_INSTANCE_ID env var)"}

    # Prefer: jobName -> build debug command
    # Only use command override if you intentionally send it
    if command_override:
        command = command_override
        print("Using command override from event.detail.command")
    else:
        if not job_name:
            return {"ok": False, "error": "Missing jobName (detail.jobName or DEFAULT_AUTOSYS_JOB env var)"}
        command = build_debug_autosys_command(job_name)
        print("Built debug autosys command from jobName")

    # Print exact command going to SSM
    print("SSM DocumentName:", document_name)
    print("SSM InstanceId:", instance_id)
    print("SSM runAsUser:", run_as_user)
    print("SSM Command (exact):", command)

    # Send SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={"command": [command], "runAsUser": [run_as_user]},
        Comment="Autosys debug start confirmation",
        CloudWatchOutputConfig={"CloudWatchOutputEnabled": True, "CloudWatchLogGroupName": cw_log_group}
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_until_done(command_id, instance_id, timeout_seconds=900, poll_seconds=3)

    stdout = (inv.get("StandardOutputContent") or "")
    stderr = (inv.get("StandardErrorContent") or "")

    evidence = extract_evidence(stdout)
    started_confirmed = any(line.strip() == "START_CONFIRMED=YES" for line in stdout.splitlines())

    plugin = get_plugin_details(command_id, instance_id)

    # IMPORTANT: return JSON-safe structure only
    return json_safe({
        "ok": True,
        "autosysJobName": job_name,
        "autosysStartedConfirmed": started_confirmed,
        "startEvidence": evidence,

        "rawStdout_first4000": stdout[:4000],
        "rawStderr_first4000": stderr[:4000],
        "rawStdout_len": len(stdout),
        "rawStderr_len": len(stderr),

        "instanceId": instance_id,
        "runAsUser": run_as_user,
        "documentName": document_name,
        "commandId": command_id,
        "cloudwatchLogGroup": cw_log_group,

        **plugin
    })