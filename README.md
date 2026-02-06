import os
import json
import time
import base64
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        inv = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )
        if inv.get("Status") in TERMINAL_STATUSES:
            return inv
        time.sleep(poll_seconds)
    raise TimeoutError("SSM command timed out")


def s3_get_json(bucket, key, timeout_seconds=240, poll_seconds=3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            return json.loads(obj["Body"].read().decode())
        except s3.exceptions.NoSuchKey:
            time.sleep(poll_seconds)
    raise TimeoutError("Evidence JSON not found")


def extract_job_name(full_cmd: str) -> str:
    """
    Extract job name after -J safely in Python
    Example:
      sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1
    """
    tokens = full_cmd.split()
    for i, tok in enumerate(tokens):
        if tok == "-J" and i + 1 < len(tokens):
            return tokens[i + 1]
    raise ValueError("Could not extract job name (-J <job>)")


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

    job_name = extract_job_name(full_cmd)

    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{run_id}.json"
    s3_key = f"{prefix}/{job_name}/{run_id}.json"

    print("FULL CMD:", full_cmd)
    print("JOB NAME:", job_name)
    print("S3 KEY:", s3_key)

    # Encode values safely
    cmd_b64 = base64.b64encode(full_cmd.encode()).decode()
    job_b64 = base64.b64encode(job_name.encode()).decode()

    remote_script = f"""#!/bin/bash
set -euo pipefail

echo "===== EC2 DEBUG START ====="
date -u
whoami
hostname
echo "=========================="

CMD="$(echo '{cmd_b64}' | base64 --decode)"
JOB="$(echo '{job_b64}' | base64 --decode)"

echo "FULL CMD:"
echo "$CMD"
echo "JOB:"
echo "$JOB"

PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  source "$PROFILE"
fi

echo "which sendevent: $(command -v sendevent)"
echo "which autorep: $(command -v autorep)"

extract_last_start() {{
  autorep -j "$JOB" 2>/dev/null | grep "$JOB" | head -n 1 | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' || true
}}

BEFORE_TS="$(extract_last_start)"
echo "BEFORE_TS=$BEFORE_TS"

CMD_SAFE="sendevent -E FORCE_STARTJOB -J \\"$JOB\\""
echo "CMD_SAFE=$CMD_SAFE"

set +e
bash -lc "$CMD_SAFE"
RC=$?
set -e

sleep 3

AFTER_TS="$(extract_last_start)"
echo "AFTER_TS=$AFTER_TS"

NOW_ISO="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

cat > "{local_file}" <<EOF
{{
  "job": "$JOB",
  "command": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "rc": "$RC",
  "capturedAtUtc": "$NOW_ISO"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"

echo "===== EC2 DEBUG END ====="
"""

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

    evidence = s3_get_json(bucket, s3_key)

    started = False
    reason = "Insufficient data"

    if evidence.get("lastStartBefore") and evidence.get("lastStartAfter"):
        if evidence["lastStartAfter"] > evidence["lastStartBefore"]:
            started = True
            reason = "Last start time increased"

    return {
        "ok": True,
        "job": job_name,
        "startedConfirmed": started,
        "reason": reason,
        "evidence": evidence,
        "ssm": {
            "commandId": command_id,
            "status": inv.get("Status"),
            "responseCode": inv.get("ResponseCode")
        }
    }