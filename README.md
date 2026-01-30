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


# ----------------------------
# JSON-safe helpers (fix MarshalError)
# ----------------------------
def json_safe(obj):
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
    if isinstance(obj, (list, tuple)):
        return [json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    return str(obj)


def _err_code(e: Exception) -> str:
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response.get("Error", {}).get("Code", "")
    return ""


# ----------------------------
# SSM polling helpers
# ----------------------------
def wait_for_invocation(command_id: str, instance_id: str, timeout_seconds: int = 300, poll_seconds: int = 2):
    """
    Workaround for InvocationDoesNotExist right after send_command.
    """
    deadline = time.time() + timeout_seconds
    last_err = None
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            return inv
        except botocore.exceptions.ClientError as e:
            last_err = e
            if _err_code(e) == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise
    raise TimeoutError(f"Invocation never appeared for {command_id} on {instance_id}. LastErr={last_err}")


def wait_until_done(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    inv = wait_for_invocation(command_id, instance_id, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = inv.get("Status")
        if status in SSM_TERMINAL:
            return inv
        time.sleep(poll_seconds)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
    raise TimeoutError(f"SSM command did not finish in time for {command_id} on {instance_id}")


def get_plugin_details(command_id: str, instance_id: str):
    """
    Details=True often contains the real stdout/stderr and timing.
    Must be JSON-sanitized to avoid datetime marshal error.
    """
    try:
        resp = ssm.list_command_invocations(CommandId=command_id, InstanceId=instance_id, Details=True)
        resp = json_safe(resp)
        invs = resp.get("CommandInvocations", [])
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


# ----------------------------
# Autosys debug command builder
# (NO SINGLE QUOTES, safe for your SSM doc's: bash -c '...; {{ command }}')
# ----------------------------
def build_debug_autosys_command(job_name: str) -> str:
    """
    Strong "started" confirmation:
      - Run autorep before
      - sendevent start
      - Run autorep after
      - START_CONFIRMED=YES if sendevent rc==0 OR autorep changed
    """
    j = (job_name or "").replace("\\", "\\\\").replace('"', '\\"')

    cmd = f"""
echo "__AUTOSYS_DEBUG_BEGIN__" 2>&1
date -Is 2>&1
echo "JOB={j}" 2>&1
echo "WHOAMI=$(whoami)" 2>&1
echo "HOST=$(hostname)" 2>&1
echo "PWD=$(pwd)" 2>&1
echo "PATH=$PATH" 2>&1

echo "__CHECK_BINARIES__" 2>&1
command -v sendevent 2>&1 || echo "MISSING:sendevent" 2>&1
command -v autostatus 2>&1 || echo "MISSING:autostatus" 2>&1
command -v autorep 2>&1 || echo "MISSING:autorep" 2>&1

echo "__BEFORE_AUTOREP__" 2>&1
BEFORE=$(autorep -J "{j}" -q 2>&1)
echo "AUTOREP_BEFORE=$BEFORE" 2>&1

echo "__STEP_SENDEVENT__" 2>&1
SE_OUT=$(sendevent -E FORCE_STARTJOB -J "{j}" 2>&1)
SE_RC=$?
echo "SENDEVENT_RC=$SE_RC" 2>&1
echo "SENDEVENT_OUTPUT=$SE_OUT" 2>&1

echo "__SLEEP__" 2>&1
sleep 5

echo "__AFTER_AUTOREP__" 2>&1
AFTER=$(autorep -J "{j}" -q 2>&1)
echo "AUTOREP_AFTER=$AFTER" 2>&1

echo "__START_CONFIRMATION_CHECK__" 2>&1
START=NO
if [ "$SE_RC" -eq 0 ]; then START=YES; fi
if [ "$BEFORE" != "$AFTER" ]; then START=YES; fi
echo "START_CONFIRMED=$START" 2>&1

echo "__AUTOSYS_DEBUG_END__" 2>&1
"""
    # one-liner for SSM parameter
    return " ".join(line.strip() for line in cmd.splitlines() if line.strip())


def extract_evidence(stdout: str):
    """
    Pull the important lines for quick viewing.
    """
    if not stdout:
        return []
    keep_prefixes = (
        "__AUTOSYS_DEBUG_",
        "__CHECK_",
        "__BEFORE_",
        "__AFTER_",
        "__STEP_",
        "__SLEEP__",
        "MISSING:",
        "AUTOREP_BEFORE=",
        "AUTOREP_AFTER=",
        "SENDEVENT_RC=",
        "SENDEVENT_OUTPUT=",
        "START_CONFIRMED="
    )
    ev = []
    for ln in stdout.splitlines():
        s = ln.strip()
        if s.startswith(keep_prefixes):
            ev.append(s)
    return ev[:400]


# ----------------------------
# Lambda handler
# ----------------------------
def lambda_handler(event, context):
    print("==== LAMBDA START ====")
    print("RAW EVENT:", json.dumps(json_safe(event)))

    detail = event.get("detail") or {}

    # Required/Defaulted inputs
    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")

    document_name = (
        detail.get("documentName")
        or os.environ.get("DOCUMENT_NAME")
        or "fundactng-shellssmdoc-stepfunc"
    )

    # Enable CloudWatch output from SSM for deeper debug
    cw_log_group = os.environ.get("SSM_CW_LOG_GROUP", "/ssm/autosys-trigger")

    # Prefer jobName -> build safe debug command (recommended)
    job_name = detail.get("jobName") or os.environ.get("DEFAULT_AUTOSYS_JOB", "")

    # Optional override: if provided, we run exactly this (be careful with quoting)
    command_override = detail.get("command")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId (detail.instanceId or DEFAULT_INSTANCE_ID env var)"}

    if command_override:
        command = command_override
        print("Using command override from event.detail.command")
    else:
        if not job_name:
            return {"ok": False, "error": "Missing jobName (detail.jobName or DEFAULT_AUTOSYS_JOB env var)"}
        command = build_debug_autosys_command(job_name)
        print("Built autosys debug command from jobName")

    # Print exact command being sent to SSM
    print("SSM DocumentName:", document_name)
    print("SSM InstanceId:", instance_id)
    print("SSM runAsUser:", run_as_user)
    print("SSM Command (exact):", command)

    # Send SSM command
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [command],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger + start confirmation",
        CloudWatchOutputConfig={
            "CloudWatchOutputEnabled": True,
            "CloudWatchLogGroupName": cw_log_group
        }
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    # Wait for completion (SSM execution completion, not Autosys completion)
    inv = wait_until_done(command_id, instance_id, timeout_seconds=900, poll_seconds=3)

    stdout = inv.get("StandardOutputContent") or ""
    stderr = inv.get("StandardErrorContent") or ""

    # Evidence + strong start confirmation flag
    evidence = extract_evidence(stdout)
    started_confirmed = any(line.strip() == "START_CONFIRMED=YES" for line in stdout.splitlines())

    # Extra plugin info (JSON safe)
    plugin = get_plugin_details(command_id, instance_id)

    # Return JSON-safe response
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