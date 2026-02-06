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


def wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        inv = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )
        if inv["Status"] in TERMINAL_STATUSES:
            return inv
        time.sleep(poll_seconds)
    raise TimeoutError("SSM command timed out")


def s3_get_json_with_retry(bucket, key, timeout_seconds=180, poll_seconds=3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(obj["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                time.sleep(poll_seconds)
                continue
            raise
    raise TimeoutError("Evidence file not found in S3")


def parse_mmddyyyy_hhmmss(s: str):
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    bucket = "fundacntg-devl-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo"

    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"
    document_name = "fundacntg-shellssmdoc-stepfunc"

    # FULL COMMAND (this is your requirement)
    full_cmd = "sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"

    run_id = str(int(time.time()))
    job_safe = sanitize(full_cmd)
    local_file = f"/tmp/autosys_{run_id}.json"
    s3_key = f"{prefix}/{job_safe}/{run_id}.json"

    cmd_b64 = base64.b64encode(full_cmd.encode()).decode()

    # ✅ IMPORTANT: NOT an f-string
    remote_script = """
#!/bin/bash
set -euo pipefail

echo "==== DEBUG ENV ===="
date -u
hostname
whoami
pwd
echo "PATH=$PATH"
echo "==================="

CMD_B64="{CMD_B64}"
CMD="$(echo "$CMD_B64" | base64 --decode)"

echo "FULL CMD (decoded):"
echo "$CMD"

# Load Autosys profile
PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  source "$PROFILE"
  echo "Autosys profile loaded"
else
  echo "Autosys profile NOT found"
fi

# Extract JOB after -J
JOB="$(echo "$CMD" | sed -n 's/.*-J \\([^ ]*\\).*/\\1/p')"
echo "Extracted JOB: $JOB"

if [ -z "$JOB" ]; then
  echo "ERROR: Job extraction failed"
  exit 2
fi

# ✅ FIX for '#': quote job explicitly
CMD_SAFE="sendevent -E FORCE_STARTJOB -J \\"$JOB\\""

echo "CMD_SAFE:"
echo "$CMD_SAFE"

extract_last_start() {
  autorep -j "$JOB" | grep "$JOB" | head -n 1 | \
  grep -Eo '[0-9]{2}/[0-9]{2}/[0-9]{4}[[:space:]]+[0-9]{2}:[0-9]{2}:[0-9]{2}' || true
}

BEFORE_TS="$(extract_last_start)"
echo "BEFORE_TS=$BEFORE_TS"

set +e
bash -lc "$CMD_SAFE"
RC=$?
set -e
echo "CMD_RC=$RC"

sleep 3

AFTER_TS="$(extract_last_start)"
echo "AFTER_TS=$AFTER_TS"

cat > "{LOCAL_FILE}" <<EOF
{
  "job": "$JOB",
  "commandOriginal": "$CMD",
  "commandExecuted": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "rc": "$RC",
  "capturedAtUtc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

aws s3 cp "{LOCAL_FILE}" "s3://{BUCKET}/{S3_KEY}"
""".format(
        CMD_B64=cmd_b64,
        LOCAL_FILE=local_file,
        BUCKET=bucket,
        S3_KEY=s3_key
    )

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        }
    )

    command_id = resp["Command"]["CommandId"]
    inv = wait_for_command(command_id, instance_id)

    print("SSM STATUS:", inv["Status"])
    print("STDOUT:", inv.get("StandardOutputContent"))
    print("STDERR:", inv.get("StandardErrorContent"))

    evidence = s3_get_json_with_retry(bucket, s3_key)

    before_ts = evidence.get("lastStartBefore")
    after_ts = evidence.get("lastStartAfter")

    started = False
    if before_ts and after_ts:
        started = parse_mmddyyyy_hhmmss(after_ts) > parse_mmddyyyy_hhmmss(before_ts)

    return {
        "ok": True,
        "autosysStarted": started,
        "before": before_ts,
        "after": after_ts,
        "s3Key": s3_key,
        "ssmStatus": inv["Status"]
    }