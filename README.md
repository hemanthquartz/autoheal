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
    # safe for filenames/keys
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s or "")


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last = inv
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last={last}")


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

    # Full command (your requirement): can come from mapping/event; keeping a default for testing
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

    run_id = str(int(time.time()))
    job_safe = sanitize(full_cmd)  # only for S3 key grouping; command itself is stored in evidence JSON
    local_file = f"/tmp/autosys_evidence_{run_id}.json"
    s3_key = f"{prefix}/{job_safe}/{run_id}.json"

    # base64 command so we can transport safely
    cmd_b64 = base64.b64encode(full_cmd.encode("utf-8")).decode("ascii")

    print("CONFIG:")
    print("  bucket:", bucket)
    print("  prefix:", prefix)
    print("  s3_key:", s3_key)
    print("  instance_id:", instance_id)
    print("  run_as_user:", run_as_user)
    print("  document_name:", document_name)
    print("  full_cmd:", full_cmd)

    # -----------------------------
    # REMOTE SCRIPT (NO f-string / NO .format)
    # Uses placeholder replacement to avoid '{ }' issues.
    # Fixes '#' issue by forcing -J "<job>"
    # Adds very verbose debug logs on EC2.
    # -----------------------------
    remote_script = r"""
#!/bin/bash
set -euo pipefail

echo "===== EC2 DEBUG START ====="
echo "UTC: $(date -u)"
echo "HOST: $(hostname)"
echo "USER: $(whoami)"
echo "PWD : $(pwd)"
echo "SHELL: $SHELL"
echo "PATH: $PATH"
echo "==========================="

echo "which bash: $(command -v bash || true)"
echo "which sendevent: $(command -v sendevent || true)"
echo "which autorep: $(command -v autorep || true)"
echo "which aws: $(command -v aws || true)"
echo "which base64: $(command -v base64 || true)"
echo "uname -a: $(uname -a || true)"
echo "---------------------------"

CMD_B64="__CMD_B64__"
LOCAL_FILE="__LOCAL_FILE__"
BUCKET="__BUCKET__"
S3_KEY="__S3_KEY__"

echo "CMD_B64 length: ${#CMD_B64}"

# Decode exactly what Lambda sent
CMD="$(echo "$CMD_B64" | base64 --decode)"

echo "FULL CMD (decoded):"
printf '%s\n' "$CMD"
echo "---------------------------"

# Load Autosys profile if present
PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  echo "Loading Autosys profile: $PROFILE"
  # shellcheck disable=SC1090
  source "$PROFILE"
  echo "Autosys profile loaded"
else
  echo "Autosys profile NOT found at: $PROFILE"
fi

echo "PATH after profile: $PATH"
echo "which sendevent after profile: $(command -v sendevent || true)"
echo "which autorep after profile: $(command -v autorep || true)"
echo "---------------------------"

# Extract JOB after -J (supports unquoted or quoted job token)
# We assume job token itself has no spaces (yours doesn't).
JOB="$(echo "$CMD" | sed -n 's/.*-J[[:space:]]*"\{0,1\}\([^"[:space:]]*\).*/\1/p')"
echo "Extracted JOB token: [$JOB]"

if [ -z "$JOB" ]; then
  echo "ERROR: Could not extract job name (-J <job>) from CMD"
  exit 2
fi

# ***** CRITICAL FIX *****
# '#' is a comment in bash unless protected by quotes.
# Build a safe command that always QUOTES the job token.
CMD_SAFE="sendevent -E FORCE_STARTJOB -J \"$JOB\""

echo "CMD_SAFE (will execute):"
printf '%s\n' "$CMD_SAFE"
echo "---------------------------"

# Capture autorep output for deep debugging
extract_last_start() {
  echo "Running autorep -j \"$JOB\" (full output captured)"
  AUTOREP_OUT="$(autorep -j "$JOB" 2>&1 || true)"
  echo "----- autorep output start -----"
  echo "$AUTOREP_OUT"
  echo "----- autorep output end -----"

  LINE="$(echo "$AUTOREP_OUT" | grep "$JOB" | head -n 1 || true)"
  echo "autorep first matching line: $LINE"

  echo "$LINE" | grep -Eo '[0-9]{2}/[0-9]{2}/[0-9]{4}[[:space:]]+[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -n 1 || true
}

echo "--- BEFORE ---"
BEFORE_TS="$(extract_last_start)"
echo "BEFORE_TS=$BEFORE_TS"

echo "--- RUN CMD_SAFE ---"
set +e
bash -lc "$CMD_SAFE" 2>&1 | tee /tmp/autosys_cmd_output.txt
RC="${PIPESTATUS[0]}"
set -e
echo "CMD_RC=$RC"

sleep 3

echo "--- AFTER ---"
AFTER_TS="$(extract_last_start)"
echo "AFTER_TS=$AFTER_TS"

NOW_ISO="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

# Write evidence JSON (simple heredoc)
cat > "$LOCAL_FILE" <<EOF
{
  "job": "$JOB",
  "commandOriginal": "$(echo "$CMD" | tr '\n' ' ')",
  "commandExecuted": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "rc": "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "hostname": "$(hostname)",
  "whoami": "$(whoami)",
  "pwd": "$(pwd)",
  "path": "$(echo "$PATH" | tr '\n' ' ')",
  "cmdOutputTail": "$(tail -n 80 /tmp/autosys_cmd_output.txt 2>/dev/null | sed 's/"/\\"/g' | tr '\n' ' ')"
}
EOF

echo "Evidence file written: $LOCAL_FILE"
echo "Evidence file tail:"
tail -n 60 "$LOCAL_FILE" || true

echo "Uploading evidence to: s3://$BUCKET/$S3_KEY"
aws s3 cp "$LOCAL_FILE" "s3://$BUCKET/$S3_KEY"

echo "===== EC2 DEBUG END ====="
"""

    # SAFE placeholder replacement (avoids .format() / f-string brace issues)
    remote_script = remote_script.replace("__CMD_B64__", cmd_b64)
    remote_script = remote_script.replace("__LOCAL_FILE__", local_file)
    remote_script = remote_script.replace("__BUCKET__", bucket)
    remote_script = remote_script.replace("__S3_KEY__", s3_key)

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
    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))
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
                reason = "Last Start increased after running command (strong confirmation job started)"
            else:
                started_confirmed = False
                reason = "Last Start did not increase (job may not have started OR timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps. before=[{before_ts}] after=[{after_ts}] err={e}"
    else:
        started_confirmed = False
        reason = "Missing before/after lastStart values in evidence. Check EC2 logs for autorep/profile."

    return {
        "ok": True,
        "fullCommandSent": full_cmd,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "commandRC": evidence.get("rc"),
        "evidenceLocation": {
            "localFileOnInstance": local_file,
            "s3Bucket": bucket,
            "s3Key": s3_key,
        },
        "ssm": {
            "commandId": command_id,
            "instanceId": instance_id,
            "documentName": document_name,
            "runAsUser": run_as_user,
            "status": inv.get("Status"),
            "responseCode": inv.get("ResponseCode"),
        },
        "debugEvidence": evidence
    }