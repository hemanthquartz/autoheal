import os
import json
import time
import re
import boto3
import botocore

ssm = boto3.client("ssm")

SSM_TERMINAL = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

# Tune these keywords to match your Autosys output in your environment.
# The goal is NOT to prove "success", only to prove "start accepted / started running".
AUTOSYS_START_KEYWORDS = [
    r"\bRUN\b", r"\bRUNNING\b", r"\bSTART\b", r"\bSTARTING\b", r"\bACTIVE\b",
    r"\bEXEC\b", r"\bEXECUTING\b", r"\bIN[_ ]PROGRESS\b", r"\bACTIVATED\b"
]

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
        if status in SSM_TERMINAL:
            return inv
        time.sleep(poll_seconds)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

    raise TimeoutError(f"Timed out waiting for command completion. {command_id=} {instance_id=}")

def _safe_single_quote(s: str) -> str:
    """Safely embed arbitrary text inside a single-quoted shell string."""
    return s.replace("'", "'\"'\"'")

def build_autosys_start_confirmation_command(job_name: str) -> str:
    """
    This command prints explicit proof tokens into stdout:
      - SENDEVENT_OUTPUT=...
      - AUTOSTATUS_OUTPUT=...
      - AUTOREP_OUTPUT=...
      - START_CONFIRMED=YES/NO
    """
    j = _safe_single_quote(job_name)

    # IMPORTANT: 2>&1 forces output into stdout so Lambda can return it.
    # We capture outputs into variables then echo them with prefixes (easy to parse).
    return (
        "bash -lc '"
        "set +e; "  # do not fail the whole script if autostatus/autorep returns non-zero
        "JOB='" + j + "'; "
        "echo \"JOB=$JOB\"; "
        "echo \"TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)\"; "
        "echo \"WHOAMI=$(whoami)\"; "
        "echo \"HOST=$(hostname)\"; "

        "echo \"STEP=CHECK_BINARIES\"; "
        "command -v sendevent >/dev/null 2>&1 && echo \"BIN_SENDEVENT=FOUND\" || echo \"BIN_SENDEVENT=MISSING\"; "
        "command -v autostatus >/dev/null 2>&1 && echo \"BIN_AUTOSTATUS=FOUND\" || echo \"BIN_AUTOSTATUS=MISSING\"; "
        "command -v autorep >/dev/null 2>&1 && echo \"BIN_AUTOREP=FOUND\" || echo \"BIN_AUTOREP=MISSING\"; "

        "echo \"STEP=SENDEVENT\"; "
        "SE_OUT=$(sendevent -E FORCE_STARTJOB -J \"$JOB\" 2>&1); "
        "SE_RC=$?; "
        "echo \"SENDEVENT_RC=$SE_RC\"; "
        "echo \"SENDEVENT_OUTPUT=$SE_OUT\"; "

        "echo \"STEP=WAIT\"; "
        "sleep 5; "

        "echo \"STEP=AUTOSTATUS\"; "
        "AS_OUT=$(autostatus -J \"$JOB\" 2>&1); "
        "AS_RC=$?; "
        "echo \"AUTOSTATUS_RC=$AS_RC\"; "
        "echo \"AUTOSTATUS_OUTPUT=$AS_OUT\"; "

        "echo \"STEP=AUTOREP\"; "
        "AR_OUT=$(autorep -J \"$JOB\" -q 2>&1); "
        "AR_RC=$?; "
        "echo \"AUTOREP_RC=$AR_RC\"; "
        "echo \"AUTOREP_OUTPUT=$AR_OUT\"; "

        # Start confirmation logic: if sendevent succeeded OR autostatus shows start/running indicators
        "START=NO; "
        "if [ \"$SE_RC\" -eq 0 ]; then START=YES; fi; "
        # Optional extra confidence: autostatus contains any running/start keyword
        "echo \"$AS_OUT\" | egrep -qi \"(RUN|RUNNING|START|STARTING|ACTIVE|EXEC|EXECUTING|IN[_ ]PROGRESS|ACTIVATED)\" && START=YES; "
        "echo \"START_CONFIRMED=$START\"; "

        "echo \"TS_DONE_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)\"; "
        "'"
    )

def parse_start_evidence(stdout: str):
    """
    Extract small, high-signal lines so your Lambda response clearly shows start proof.
    """
    lines = stdout.splitlines() if stdout else []
    evidence = []
    want_prefixes = (
        "JOB=", "TS_UTC=", "WHOAMI=", "HOST=",
        "BIN_", "STEP=",
        "SENDEVENT_RC=", "SENDEVENT_OUTPUT=",
        "AUTOSTATUS_RC=", "AUTOSTATUS_OUTPUT=",
        "AUTOREP_RC=", "AUTOREP_OUTPUT=",
        "START_CONFIRMED=",
        "TS_DONE_UTC="
    )
    for ln in lines:
        if ln.startswith(want_prefixes):
            evidence.append(ln)
    # keep response small but useful
    return evidence[:200]

def lambda_handler(event, context):
    """
    Input event (EventBridge or test):
      {
        "detail": {
          "instanceId": "i-xxxxxxxx",
          "runAsUser": "bk6dev1",
          "jobName": "GV7#SAM#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
        }
      }

    You can also pass:
      detail.command  -> overrides command creation entirely (advanced).
    """
    print("EVENT:", json.dumps(event))

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    job_name = detail.get("jobName") or os.environ.get("DEFAULT_AUTOSYS_JOB", "")
    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")
    cw_log_group = os.environ.get("SSM_CW_LOG_GROUP", "/ssm/autosys-trigger")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId (detail.instanceId or DEFAULT_INSTANCE_ID env var)"}

    # Build a command that prints explicit start confirmation tokens
    command = detail.get("command")
    if not command:
        if not job_name:
            return {
                "ok": False,
                "error": "Missing jobName and command. Provide detail.jobName or detail.command (or DEFAULT_AUTOSYS_JOB env var)."
            }
        command = build_autosys_start_confirmation_command(job_name)

    # 1) Send SSM command
    try:
        resp = ssm.send_command(
            DocumentName=document_name,
            InstanceIds=[instance_id],
            Parameters={
                "command": [command],
                "runAsUser": [run_as_user],
            },
            Comment=f"Autosys start confirmation via {document_name}",
            CloudWatchOutputConfig={
                "CloudWatchOutputEnabled": True,
                "CloudWatchLogGroupName": cw_log_group
            }
        )
    except botocore.exceptions.ClientError as e:
        return {"ok": False, "error": "send_command failed", "details": str(e)}

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    # 2) Wait until command finishes so we can collect stdout/stderr
    try:
        inv = wait_until_done(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    except Exception as e:
        return {
            "ok": False,
            "error": "Failed waiting for completion",
            "instanceId": instance_id,
            "runAsUser": run_as_user,
            "documentName": document_name,
            "commandId": command_id,
            "cloudwatchLogGroup": cw_log_group,
            "details": str(e)
        }

    stdout = (inv.get("StandardOutputContent") or "").strip()
    stderr = (inv.get("StandardErrorContent") or "").strip()

    # Parse explicit proof line
    start_confirmed = False
    for ln in stdout.splitlines():
        if ln.strip() == "START_CONFIRMED=YES":
            start_confirmed = True
            break

    # Return ONLY what you care about: did the command start the Autosys job + evidence
    return {
        "ok": True,  # lambda completed; do not confuse with autosys success
        "autosysJobName": job_name,
        "autosysStartedConfirmed": start_confirmed,  # strong confirmation flag
        "startEvidence": parse_start_evidence(stdout),  # includes SENDEVENT_OUTPUT + AUTOSTATUS_OUTPUT
        "autosysStdErr": stderr,  # keep if something fails
        "instanceId": instance_id,
        "runAsUser": run_as_user,
        "documentName": document_name,
        "commandId": command_id,
        "cloudwatchLogGroup": cw_log_group
    }