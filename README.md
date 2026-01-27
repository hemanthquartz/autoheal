import os
import json
import time
import boto3
import botocore
import re

ssm = boto3.client("ssm")

# ---------- helpers (SSM eventual consistency) ----------
def _err_code(e: Exception) -> str:
    if isinstance(e, botocore.exceptions.ClientError):
        return e.response.get("Error", {}).get("Code", "")
    return ""

def wait_for_invocation(command_id: str, instance_id: str, timeout_seconds: int = 120, poll_seconds: int = 2):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            return ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except botocore.exceptions.ClientError as e:
            if _err_code(e) == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise
    raise TimeoutError(f"Timed out waiting for invocation. command_id={command_id}, instance_id={instance_id}")

def run_ssm_and_get_output(document_name: str, instance_id: str, run_as_user: str, command: str, timeout_seconds: int = 300):
    """Send SSM command and return stdout/stderr. (We use SSM only as transport, not as 'status'.)"""
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={"command": [command], "runAsUser": [run_as_user]},
        Comment="Autosys trigger/status check"
    )

    command_id = resp["Command"]["CommandId"]

    inv = wait_for_invocation(command_id, instance_id, timeout_seconds=min(timeout_seconds, 120))
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        status = inv.get("Status")
        if status in {"Success", "Failed", "TimedOut", "Cancelled"}:
            return {
                "commandId": command_id,
                "stdout": inv.get("StandardOutputContent", "") or "",
                "stderr": inv.get("StandardErrorContent", "") or "",
                "transportStatus": status
            }
        time.sleep(2)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

    # still return whatever we have
    return {
        "commandId": command_id,
        "stdout": inv.get("StandardOutputContent", "") or "",
        "stderr": inv.get("StandardErrorContent", "") or "",
        "transportStatus": inv.get("Status", "Unknown")
    }

# ---------- Autosys parsing ----------
def parse_autosys_status(autostatus_output: str) -> str:
    """
    Try to extract job status from autostatus output.
    Different autosys setups vary; we return best-effort status token.
    """
    txt = (autostatus_output or "").strip()
    if not txt:
        return "UNKNOWN"

    upper = txt.upper()

    # Common statuses that often appear in output
    for token in ["SUCCESS", "FAILURE", "FAILED", "RUNNING", "STARTING", "ACTIVE", "INACTIVE", "ON_ICE", "ON_HOLD", "TERMINATED"]:
        if token in upper:
            if token == "FAILED":
                return "FAILURE"
            return token

    # Sometimes output includes something like: "Status: RUNNING"
    m = re.search(r"STATUS\s*[:=]\s*([A-Z_]+)", upper)
    if m:
        return m.group(1)

    return "UNKNOWN"

def classify_terminal(status_token: str) -> bool:
    return status_token in {"SUCCESS", "FAILURE", "TERMINATED"}

# ---------- main ----------
def lambda_handler(event, context):
    """
    Expected event.detail:
      instanceId (required)
      runAsUser  (required/optional)
      jobName    (required)
      forceStart (optional true/false)
      pollSeconds (optional, default 15)
      maxWaitSeconds (optional, default 600)

    Output: Autosys job status + proof outputs from autostatus/autorep
    """

    detail = event.get("detail") or {}

    instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
    run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER", "ec2-user")
    job_name = detail.get("jobName")
    force_start = bool(detail.get("forceStart", True))

    poll_seconds = int(detail.get("pollSeconds", 15))
    max_wait_seconds = int(detail.get("maxWaitSeconds", 600))

    document_name = os.environ.get("DOCUMENT_NAME", "fundactng-shellssmdoc-stepfunc")

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId"}
    if not job_name:
        return {"ok": False, "error": "Missing jobName"}

    # 1) Trigger the job
    start_cmd = f'sendevent -E {"FORCE_STARTJOB" if force_start else "STARTJOB"} -J "{job_name}"'
    trigger = run_ssm_and_get_output(document_name, instance_id, run_as_user, start_cmd, timeout_seconds=120)

    # 2) Poll Autosys for job status (this is the REAL status you want)
    # We'll use autostatus first; autorep is added as extra proof at the end.
    deadline = time.time() + max_wait_seconds
    history = []

    last_status = "UNKNOWN"
    last_autostatus_out = ""
    last_autostatus_err = ""

    while time.time() < deadline:
        status_cmd = f'autostatus -J "{job_name}"'
        chk = run_ssm_and_get_output(document_name, instance_id, run_as_user, status_cmd, timeout_seconds=120)

        out = chk["stdout"]
        err = chk["stderr"]
        status_token = parse_autosys_status(out)

        history.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "autosysStatus": status_token,
            "autostatusStdoutSample": out[:500],
            "autostatusStderrSample": err[:300],
        })

        last_status = status_token
        last_autostatus_out = out
        last_autostatus_err = err

        if classify_terminal(status_token):
            break

        time.sleep(poll_seconds)

    # 3) Extra proof: autorep summary (optional but useful)
    rep_cmd = f'autorep -J "{job_name}" -q'
    rep = run_ssm_and_get_output(document_name, instance_id, run_as_user, rep_cmd, timeout_seconds=120)

    # Decide success based on Autosys status, not SSM
    ok = (last_status == "SUCCESS")

    return {
        "ok": ok,
        "jobName": job_name,
        "autosysStatus": last_status,               # <---- THIS is what you asked for
        "polledForSeconds": max_wait_seconds,
        "pollSeconds": poll_seconds,

        # Proof outputs
        "triggerCommand": start_cmd,
        "triggerStdout": trigger.get("stdout", ""),
        "triggerStderr": trigger.get("stderr", ""),

        "finalAutostatusStdout": last_autostatus_out,
        "finalAutostatusStderr": last_autostatus_err,

        "autorepStdout": rep.get("stdout", ""),
        "autorepStderr": rep.get("stderr", ""),

        # small history so you can see progression (RUNNING -> SUCCESS/FAILURE)
        "statusChecks": history[-10:],  # keep last 10 checks
    }