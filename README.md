import os
import json
import time
import re
import base64
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    # safe for S3 key grouping (not for execution)
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s or "")


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    """
    Robust waiter for SSM command invocation.
    IMPORTANT: InvocationDoesNotExist is normal immediately after send_command.
    """
    deadline = time.time() + timeout_seconds
    last_error = None
    last_status = None

    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last_status = inv.get("Status")

            # keep printing for debugging
            print("SSM poll:", {"commandId": command_id, "instanceId": instance_id, "status": last_status})

            if last_status in TERMINAL_STATUSES:
                return inv

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "InvocationDoesNotExist":
                # Normal race: invocation not created yet
                last_error = code
                print("SSM poll: InvocationDoesNotExist (normal), retrying...")
                time.sleep(poll_seconds)
                continue
            raise

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Timed out waiting for SSM command {command_id} on {instance_id}. "
        f"last_status={last_status} last_error={last_error}"
    )


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 240, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_err = None
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8", errors="replace")
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(poll_seconds)

    raise TimeoutError(f"Evidence JSON not found in time s3://{bucket}/{key}. Last error: {last_err}")


def parse_mmddyyyy_hhmmss(s: str):
    # Example: 01/30/2026 02:41:11
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def extract_job_name_from_full_cmd(full_cmd: str) -> str:
    """
    Extract job token after -J from the FULL command.
    Assumes job token itself has no spaces (your Autosys job tokens do not).
    """
    parts = (full_cmd or "").strip().split()
    for i, tok in enumerate(parts):
        if tok == "-J" and i + 1 < len(parts):
            return parts[i + 1]
    raise ValueError(f"Could not extract job name from full command (missing -J <job>): {full_cmd}")


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # -----------------------------
    # CONFIG (keep your existing values here)
    # -----------------------------
    bucket = os.environ.get("AUTOSYS_EVIDENCE_BUCKET", "fundacntg-devl-ftbu-us-east-1")
    prefix = os.environ.get("AUTOSYS_EVIDENCE_PREFIX", "prepare/cin/dflt/SAM/test_ybyo").strip("/")

    detail = event.get("detail") or {}

    instance_id = os.environ.get("AUTOSYS_INSTANCE_ID", "i-090e6f0a08fa26397")
    run_as_user = os.environ.get("AUTOSYS_RUN_AS_USER", "gauhlk")
    document_name = event.get("documentName") or detail.get("documentName") or os.environ.get(
        "AUTOSYS_DOCUMENT_NAME", "fundacntg-shellssmdoc-stepfunc"
    )

    # Full command (your requirement)
    full_cmd = (
        event.get("jobCommand")
        or detail.get("jobCommand")
        or event.get("job_name")
        or detail.get("job_name")
        or "sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
    ).strip()

    if not bucket:
        return {"ok": False, "error": "Missing evidence bucket. Set AUTOSYS_EVIDENCE_BUCKET env var."}
    if not instance_id or not full_cmd:
        return {"ok": False, "error": "Missing instanceId or full command (jobCommand/job_name)"}

    # Extract job name in Python (avoid awk/sed parsing issues on EC2)
    job_name = extract_job_name_from_full_cmd(full_cmd)

    run_id = str(int(time.time()))
    # Keep evidence S3 key readable and safe
    job_safe = sanitize(job_name)
    local_file = f"/tmp/autosys_evidence_{run_id}.json"
    s3_key = f"{prefix}/{job_safe}/{run_id}.json"

    # base64 command and job so we can transport safely
    cmd_b64 = base64.b64encode(full_cmd.encode("utf-8")).decode("ascii")
    job_b64 = base64.b64encode(job_name.encode("utf-8")).decode("ascii")

    print("CONFIG:")
    print("  bucket:", bucket)
    print("  prefix:", prefix)
    print("  s3_key:", s3_key)
    print("  instance_id:", instance_id)
    print("  run_as_user:", run_as_user)
    print("  document_name:", document_name)
    print("  full_cmd:", full_cmd)
    print("  extracted_job_name:", job_name)

    # -----------------------------
    # REMOTE SCRIPT
    # - No awk/sed parsing for job (done in Python)
    # - Fixes '#' issue by quoting -J "<job>"
    # - Writes evidence JSON locally and uploads to S3
    # - Adds strong debug logging on EC2
    #
    # NOTE: this IS an f-string, but we escape braces using double {{ }} only
    #       for the function body regex portions (grep -Eo). Everything else is safe.
    # -----------------------------
    remote_script = f"""#!/bin/bash
set -euo pipefail

echo "===== EC2 DEBUG START ====="
echo "UTC: $(date -u)"
echo "HOST: $(hostname)"
echo "USER: $(whoami)"
echo "PWD : $(pwd)"
echo "SHELL: $SHELL"
echo "PATH: $PATH"
echo "==========================="

CMD="$(echo '{cmd_b64}' | base64 --decode)"
JOB="$(echo '{job_b64}' | base64 --decode)"

echo "FULL CMD (decoded):"
printf '%s\\n' "$CMD"
echo "JOB (decoded):"
printf '%s\\n' "$JOB"

PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  echo "Loading Autosys profile: $PROFILE"
  source "$PROFILE"
  echo "Autosys profile loaded"
else
  echo "Autosys profile NOT found at: $PROFILE"
fi

echo "which sendevent after profile: $(command -v sendevent || true)"
echo "which autorep after profile: $(command -v autorep || true)"

extract_last_start() {{
  # Return MM/DD/YYYY HH:MM:SS if found
  autorep -j "$JOB" 2>&1 | grep "$JOB" | head -n 1 | \
    grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

echo "--- BEFORE ---"
BEFORE_TS="$(extract_last_start)"
echo "BEFORE_TS=$BEFORE_TS"

# ***** CRITICAL FIX *****
# '#' is a comment in bash unless protected by quotes.
CMD_SAFE="sendevent -E FORCE_STARTJOB -J \\"$JOB\\""
echo "CMD_SAFE=$CMD_SAFE"

echo "--- RUN ---"
set +e
bash -lc "$CMD_SAFE" 2>&1 | tee /tmp/autosys_cmd_output.txt
RC="${{PIPESTATUS[0]}}"
set -e
echo "CMD_RC=$RC"

sleep 3

echo "--- AFTER ---"
AFTER_TS="$(extract_last_start)"
echo "AFTER_TS=$AFTER_TS"

NOW_ISO="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

cat > "{local_file}" <<EOF
{{
  "job": "$JOB",
  "commandOriginal": "$(echo "$CMD" | tr '\\n' ' ')",
  "commandExecuted": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "rc": "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "hostname": "$(hostname)",
  "whoami": "$(whoami)",
  "pwd": "$(pwd)",
  "path": "$(echo "$PATH" | tr '\\n' ' ')",
  "cmdOutputTail": "$(tail -n 120 /tmp/autosys_cmd_output.txt 2>/dev/null | sed 's/"/\\\\\\"/g' | tr '\\n' ' ')"
}}
EOF

echo "Uploading evidence to S3: s3://{bucket}/{s3_key}"
aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"

echo "===== EC2 DEBUG END ====="
"""

    # Send to SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger (full command) + evidence saved locally and uploaded to S3",
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("SSM Final Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))
    print("SSM Stdout (first 4000 chars):", (inv.get("StandardOutputContent") or "")[:4000])
    print("SSM Stderr (first 4000 chars):", (inv.get("StandardErrorContent") or "")[:4000])

    # Read evidence JSON from S3 (NOT stdout/stderr, NOT Parameter Store)
    evidence = s3_get_json_with_retry(bucket, s3_key, timeout_seconds=240, poll_seconds=3)

    before_ts = (evidence.get("lastStartBefore") or "").strip()
    after_ts = (evidence.get("lastStartAfter") or "").strip()

    started_confirmed = False
    reason = None

    if before_ts and after_ts:
        try:
            dt_before = parse_mmddyyyy_hhmmss(before_ts)
            dt_after = parse_mmddyyyy_hhmmss(after_ts)
            if dt_after > dt_before:
                started_confirmed = True
                reason = "Last Start increased after send event (strong confirmation job started)"
            else:
                started_confirmed = False
                reason = "Last Start did not increase (job may not have started OR timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps. before=[{before_ts}] after=[{after_ts}] err={e}"
    else:
        started_confirmed = False
        reason = "Missing before/after lastStart values in evidence. Check EC2 logs (cmdOutputTail/profile)."

    return {
        "ok": True,
        "jobName": job_name,
        "fullCommandSent": full_cmd,
        "startedConfirmed": started_confirmed,
        "reason": reason,
        "evidence": evidence,
        "evidenceLocation": {"s3Bucket": bucket, "s3Key": s3_key, "localFileOnInstance": local_file},
        "ssm": {
            "commandId": command_id,
            "instanceId": instance_id,
            "documentName": document_name,
            "runAsUser": run_as_user,
            "status": inv.get("Status"),
            "responseCode": inv.get("ResponseCode"),
        },
    }