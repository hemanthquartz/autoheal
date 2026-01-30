import os
import json
import time
import boto3
import botocore
import re
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
    Details=True often contains extra timing/metadata; sanitize for JSON.
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
# Autosys: command builder (robust "started" confirmation)
#   Confirmation based on:
#     - SENDEVENT_RC==0 (request accepted)
#     - OR full autorep row changed
#     - OR LastStart changed (and after >= before)
# ----------------------------
def build_debug_autosys_command(job_name: str) -> str:
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
command -v autorep 2>&1 || echo "MISSING:autorep" 2>&1
command -v autostatus 2>&1 || echo "MISSING:autostatus" 2>&1

echo "__BEFORE_AUTOREP__" 2>&1
BEFORE_RAW=$(autorep -J "{j}" -q 2>&1)
echo "AUTOREP_BEFORE_RAW_BEGIN" 2>&1
echo "$BEFORE_RAW" 2>&1
echo "AUTOREP_BEFORE_RAW_END" 2>&1
BEFORE_LINE=$(echo "$BEFORE_RAW" | grep -E "^{j}[[:space:]]" | tail -n 1)
if [ -z "$BEFORE_LINE" ]; then BEFORE_LINE=$(echo "$BEFORE_RAW" | tail -n 1); fi
echo "AUTOREP_BEFORE_LINE=$BEFORE_LINE" 2>&1
BEFORE_START=$(echo "$BEFORE_LINE" | awk '{{print $2" "$3}}')
echo "AUTOREP_BEFORE_LASTSTART=$BEFORE_START" 2>&1

echo "__SENDEVENT__" 2>&1
SE_OUT=$(sendevent -E FORCE_STARTJOB -J "{j}" 2>&1)
SE_RC=$?
echo "SENDEVENT_RC=$SE_RC" 2>&1
echo "SENDEVENT_OUTPUT=$SE_OUT" 2>&1

echo "__SLEEP__" 2>&1
sleep 5

echo "__AFTER_AUTOREP__" 2>&1
AFTER_RAW=$(autorep -J "{j}" -q 2>&1)
echo "AUTOREP_AFTER_RAW_BEGIN" 2>&1
echo "$AFTER_RAW" 2>&1
echo "AUTOREP_AFTER_RAW_END" 2>&1
AFTER_LINE=$(echo "$AFTER_RAW" | grep -E "^{j}[[:space:]]" | tail -n 1)
if [ -z "$AFTER_LINE" ]; then AFTER_LINE=$(echo "$AFTER_RAW" | tail -n 1); fi
echo "AUTOREP_AFTER_LINE=$AFTER_LINE" 2>&1
AFTER_START=$(echo "$AFTER_LINE" | awk '{{print $2" "$3}}')
echo "AUTOREP_AFTER_LASTSTART=$AFTER_START" 2>&1

echo "__START_CONFIRMATION_CHECK__" 2>&1
START=NO
REASON="none"

# 1) sendevent accepted
if [ "$SE_RC" -eq 0 ]; then
  START=YES
  REASON="sendevent_rc_0"
fi

# 2) full autorep row changed (very robust)
if [ "$BEFORE_LINE" != "$AFTER_LINE" ] && [ -n "$AFTER_LINE" ]; then
  START=YES
  if [ "$REASON" = "none" ]; then REASON="autorep_line_changed"; else REASON="$REASON,autorep_line_changed"; fi
fi

# 3) laststart changed (and not empty) — expected to be newer; if older, treat as parse issue but still keep line-changed logic
if [ -n "$BEFORE_START" ] && [ -n "$AFTER_START" ] && [ "$BEFORE_START" != "$AFTER_START" ]; then
  START=YES
  if [ "$REASON" = "none" ]; then REASON="laststart_changed"; else REASON="$REASON,laststart_changed"; fi
fi

echo "START_CONFIRMED=$START" 2>&1
echo "START_REASON=$REASON" 2>&1

echo "__AUTOSYS_DEBUG_END__" 2>&1
"""
    # one-liner for SSM parameter
    return " ".join(line.strip() for line in cmd.splitlines() if line.strip())


# ----------------------------
# Parse helpers
# ----------------------------
def find_kv(stdout: str, key: str):
    if not stdout:
        return None
    for ln in stdout.splitlines():
        if ln.startswith(key + "="):
            return ln.split("=", 1)[1].strip()
    return None


def parse_autosys_mmddyyyy_hhmmss(ts: str):
    """
    Autosys: MM/DD/YYYY HH:MM:SS  -> return sortable ISO (no tz)
    """
    if not ts:
        return None
    ts = ts.strip()
    if not re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$", ts):
        return None
    mm, dd, yyyy = ts[0:2], ts[3:5], ts[6:10]
    hh, mi, ss = ts[11:13], ts[14:16], ts[17:19]
    return f"{yyyy}-{mm}-{dd}T{hh}:{mi}:{ss}"


def extract_evidence(stdout: str, max_lines: int = 500):
    if not stdout:
        return []
    keep = (
        "__AUTOSYS_DEBUG_",
        "__CHECK_",
        "__BEFORE_",
        "__AFTER_",
        "__SENDEVENT__",
        "__SLEEP__",
        "__START_CONFIRMATION_CHECK__",
        "MISSING:",
        "AUTOREP_BEFORE_LINE=",
        "AUTOREP_AFTER_LINE=",
        "AUTOREP_BEFORE_LASTSTART=",
        "AUTOREP_AFTER_LASTSTART=",
        "SENDEVENT_RC=",
        "SENDEVENT_OUTPUT=",
        "START_CONFIRMED=",
        "START_REASON=",
    )
    out = []
    for ln in stdout.splitlines():
        s = ln.strip()
        if s.startswith(keep):
            out.append(s)
    return out[:max_lines]


# ----------------------------
# Lambda handler
# ----------------------------
def lambda_handler(event, context):
    print("==== LAMBDA START ====")
    print("RAW EVENT:", json.dumps(json_safe(event)))

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")

    document_name = (
        detail.get("documentName")
        or os.environ.get("DOCUMENT_NAME")
        or "fundactng-shellssmdoc-stepfunc"
    )

    cw_log_group = os.environ.get("SSM_CW_LOG_GROUP", "/ssm/autosys-trigger")

    job_name = detail.get("jobName") or os.environ.get("DEFAULT_AUTOSYS_JOB", "")
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

    print("SSM DocumentName:", document_name)
    print("SSM InstanceId:", instance_id)
    print("SSM runAsUser:", run_as_user)
    print("SSM Command (exact):", command)

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [command],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger + start confirmation (autorep last start)",
        CloudWatchOutputConfig={
            "CloudWatchOutputEnabled": True,
            "CloudWatchLogGroupName": cw_log_group
        }
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_until_done(command_id, instance_id, timeout_seconds=900, poll_seconds=3)

    stdout = inv.get("StandardOutputContent") or ""
    stderr = inv.get("StandardErrorContent") or ""

    # Parse key outputs
    before_line = find_kv(stdout, "AUTOREP_BEFORE_LINE")
    after_line = find_kv(stdout, "AUTOREP_AFTER_LINE")
    before_ls_raw = find_kv(stdout, "AUTOREP_BEFORE_LASTSTART")
    after_ls_raw = find_kv(stdout, "AUTOREP_AFTER_LASTSTART")
    se_rc = find_kv(stdout, "SENDEVENT_RC")
    se_out = find_kv(stdout, "SENDEVENT_OUTPUT")
    start_flag = find_kv(stdout, "START_CONFIRMED")
    start_reason = find_kv(stdout, "START_REASON")

    before_ls_iso = parse_autosys_mmddyyyy_hhmmss(before_ls_raw)
    after_ls_iso = parse_autosys_mmddyyyy_hhmmss(after_ls_raw)

    # Confirmation signals:
    line_changed = (before_line is not None and after_line is not None and before_line != after_line)
    laststart_changed = (before_ls_iso is not None and after_ls_iso is not None and before_ls_iso != after_ls_iso)

    # "After older than before" is NOT confirmation; treat as parse/sampling issue
    laststart_after_older = (
        before_ls_iso is not None and after_ls_iso is not None and after_ls_iso < before_ls_iso
    )

    # Final decision: require one strong signal
    autosys_started_confirmed = (
        (start_flag == "YES")
        or line_changed
        or (laststart_changed and not laststart_after_older)
        or (se_rc == "0")  # accepted by scheduler, weaker but still useful
    )

    evidence = extract_evidence(stdout)

    plugin = get_plugin_details(command_id, instance_id)

    return json_safe({
        "ok": True,

        "autosysJobName": job_name,

        # main result
        "autosysStartedConfirmed": autosys_started_confirmed,
        "autosysStartReason": start_reason,

        # strongest confirmations
        "autorepLineChanged": line_changed,
        "autosysLastStartBefore": before_ls_raw,
        "autosysLastStartAfter": after_ls_raw,
        "autosysLastStartBeforeIso": before_ls_iso,
        "autosysLastStartAfterIso": after_ls_iso,
        "autosysLastStartChanged": laststart_changed,
        "autosysLastStartAfterOlderThanBefore": laststart_after_older,

        # sendevent info
        "sendeventRc": se_rc,
        "sendeventOutput": se_out,

        # quick evidence lines
        "startEvidence": evidence,

        # raw logs for debugging
        "rawStdout_first4000": stdout[:4000],
        "rawStderr_first4000": stderr[:4000],
        "rawStdout_len": len(stdout),
        "rawStderr_len": len(stderr),

        # ssm tracking
        "instanceId": instance_id,
        "runAsUser": run_as_user,
        "documentName": document_name,
        "commandId": command_id,
        "cloudwatchLogGroup": cw_log_group,

        # plugin details
        **plugin
    })