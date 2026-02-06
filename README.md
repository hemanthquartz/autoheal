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
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", s or "")


def wait_for_command(command_id, instance_id, timeout=900, poll=3):
    end = time.time() + timeout
    while time.time() < end:
        try:
            inv = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvocationDoesNotExist":
                time.sleep(poll)
                continue
            raise

        if inv["Status"] in TERMINAL_STATUSES:
            return inv
        time.sleep(poll)

    raise TimeoutError("SSM command timed out")


def s3_get_json_with_retry(bucket, key, timeout=240, poll=3):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(obj["Body"].read().decode())
        except Exception as e:
            last = e
            time.sleep(poll)
    raise TimeoutError(f"S3 evidence not found: {last}")


def parse_mmddyyyy_hhmmss(s):
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    bucket = "fundacntg-devl-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo"

    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"
    document_name = "fundacntg-shellssmdoc-stepfunc"

    full_cmd = (
        event.get("jobCommand")
        or "sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
    )

    run_id = str(int(time.time()))
    job_safe = sanitize(full_cmd)
    local_file = f"/tmp/autosys_evidence_{run_id}.json"
    s3_key = f"{prefix}/{job_safe}/{run_id}.json"

    cmd_b64 = base64.b64encode(full_cmd.encode()).decode()

    print("CONFIG:")
    print("bucket:", bucket)
    print("s3_key:", s3_key)
    print("full_cmd:", full_cmd)

    remote_script = r"""#!/bin/bash
set -euo pipefail

echo "===== EC2 DEBUG START ====="
date -u
whoami
hostname
pwd
echo "PATH=$PATH"

CMD_B64="__CMD_B64__"
LOCAL_FILE="__LOCAL_FILE__"
BUCKET="__BUCKET__"
S3_KEY="__S3_KEY__"

CMD="$(echo "$CMD_B64" | base64 --decode)"

echo "FULL CMD:"
echo "$CMD"

# Load Autosys profile
PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  source "$PROFILE"
fi

which sendevent || true
which autorep || true

# ===== SAFE JOB EXTRACTION (NO awk/sed) =====
JOB="${CMD#*-J }"
JOB="${JOB%% *}"

echo "Extracted JOB=[$JOB]"

if [ -z "$JOB" ]; then
  echo "ERROR: Failed to extract job name"
  exit 2
fi

CMD_SAFE="sendevent -E FORCE_STARTJOB -J \"$JOB\""
echo "CMD_SAFE=$CMD_SAFE"

extract_last_start() {
  autorep -j "$JOB" 2>&1 | grep "$JOB" | head -n 1 | \
    grep -Eo '[0-9]{2}/[0-9]{2}/[0-9]{4}[[:space:]]+[0-9]{2}:[0-9]{2}:[0-9]{2}' || true
}

BEFORE_TS="$(extract_last_start)"
bash -lc "$CMD_SAFE"
RC=$?
sleep 3
AFTER_TS="$(extract_last_start)"

NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$LOCAL_FILE" <<EOF
{
  "job": "$JOB",
  "command": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "rc": "$RC",
  "capturedAtUtc": "$NOW_ISO"
}
EOF

aws s3 cp "$LOCAL_FILE" "s3://$BUCKET/$S3_KEY"
echo "===== EC2 DEBUG END ====="
"""

    remote_script = (
        remote_script
        .replace("__CMD_B64__", cmd_b64)
        .replace("__LOCAL_FILE__", local_file)
        .replace("__BUCKET__", bucket)
        .replace("__S3_KEY__", s3_key)
    )

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user]
        }
    )

    command_id = resp["Command"]["CommandId"]
    inv = wait_for_command(command_id, instance_id)

    evidence = s3_get_json_with_retry(bucket, s3_key)

    before_ts = evidence.get("lastStartBefore", "")
    after_ts = evidence.get("lastStartAfter", "")

    started = False
    reason = "unknown"

    if before_ts and after_ts:
        if parse_mmddyyyy_hhmmss(after_ts) > parse_mmddyyyy_hhmmss(before_ts):
            started = True
            reason = "Last start increased"

    return {
        "ok": True,
        "autosysStartedConfirmed": started,
        "reason": reason,
        "evidence": evidence,
        "ssm": {
            "commandId": command_id,
            "status": inv["Status"],
            "responseCode": inv["ResponseCode"]
        }
    }