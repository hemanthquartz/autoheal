import json
import time
import re
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._\-\/]", "_", s)


def wait_for_command(command_id: str, instance_id: str,
                     timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            print("[DEBUG] get_command_invocation error:", code)
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        print("[DEBUG] SSM Invocation:", json.dumps(inv, indent=2))
        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(
        f"Timed out waiting for SSM command {command_id} on {instance_id}"
    )


def s3_get_json_with_retry(bucket: str, key: str,
                           timeout_seconds: int = 180, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_err = None

    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8")
            print("[DEBUG] Evidence JSON body:", body)
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = e.response.get("Error", {}).get("Code", "")
            print("[DEBUG] Waiting for evidence JSON, error:", code)
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(poll_seconds)

    raise TimeoutError(
        f"Evidence JSON not found in time s3://{bucket}/{key}. "
        f"Last error: {last_err}"
    )


def parse_mmddyyyy_hhmmss(s: str):
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo/"

    detail = event.get("detail") or {}

    instance_id = "i-090e6f0a08fa26397"
    job_name = "sendevent -E FORCE_STARTJOB -j GV7#SAM#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
    run_as_user = "gauhlk"
    document_name = (
        event.get("documentName")
        or detail.get("documentName")
        or "fundacntg-shellssmdoc-stepfunc"
    )

    if not instance_id or not job_name:
        return {"ok": False, "error": "Missing instanceId or jobName"}

    job_safe = sanitize(job_name)
    run_id = str(int(time.time()))

    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] job_name:", job_name)
    print("[DEBUG] run_as_user:", run_as_user)
    print("[DEBUG] document_name:", document_name)
    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] s3_key:", s3_key)

    remote_script = f"""
set -e

JOB="{job_name}"

echo "[DEBUG] Running as user: $(whoami)"
echo "[DEBUG] JOB=$JOB"

if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' || true
}}

BEFORE_TS=$(extract_last_start)
echo "[DEBUG] BEFORE_TS=$BEFORE_TS"

{job_name}
RC=$?

sleep 3

AFTER_TS=$(extract_last_start)
NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_name}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"
""".strip()

    print("[DEBUG] Remote script:\n", remote_script)

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user]
        },
        Comment="Autosys trigger + evidence saved locally and uploaded to S3"
    )

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id)
    print("SSM Status:", inv.get("Status"), inv.get("ResponseCode"))

    evidence = s3_get_json_with_retry(bucket, s3_key)

    before_ts = (evidence.get("lastStartBefore") or "").strip()
    after_ts = (evidence.get("lastStartAfter") or "").strip()

    started_confirmed = False
    reason = None

    if before_ts and after_ts:
        dt_before = parse_mmddyyyy_hhmmss(before_ts)
        dt_after = parse_mmddyyyy_hhmmss(after_ts)
        if dt_after > dt_before:
            started_confirmed = True
            reason = "Last Start increased after sendevent (strong confirmation job started)"
        else:
            reason = "Last Start did not increase"
    else:
        reason = "Missing before/after lastStart values in evidence file"

    return {
        "ok": True,
        "autosysJobName": job_name,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendeventRc": evidence.get("sendeventRc"),
        "evidenceLocation": {
            "localFileOnInstance": local_file,
            "s3Bucket": bucket,
            "s3Key": s3_key
        },
        "ssm": {
            "commandId": command_id,
            "instanceId": instance_id,
            "documentName": document_name,
            "runAsUser": run_as_user,
            "status": inv.get("Status"),
            "responseCode": inv.get("ResponseCode")
        }
    }