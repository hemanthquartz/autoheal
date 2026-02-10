import json
import time
import re
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._\-\/]", "_", s)


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}")


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 120, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_err = None
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8")
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


def load_job_mapping(filename: str = "autosys_job_mapping.json") -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    print("[DEBUG] Loading mapping:", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("[DEBUG] Mapping keys:", list(data.keys()))
    return data


def extract_s3_key_from_event(event: dict) -> str:
    """
    Supports EventBridge/CloudTrail style events.
    Prefer: detail.requestParameters.key
    Fallback: resources[].ARN for s3 object.
    """
    detail = event.get("detail") or {}
    req = detail.get("requestParameters") or {}
    key = req.get("key")
    if isinstance(key, str) and key.strip():
        print("[DEBUG] S3 key from detail.requestParameters.key:", key)
        return key

    resources = event.get("resources") or []
    for r in resources:
        arn = r.get("ARN") or r.get("arn")
        if isinstance(arn, str) and arn.startswith("arn:aws:s3:::") and "/" in arn:
            k = arn.split("arn:aws:s3:::")[-1]
            parts = k.split("/", 1)
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find S3 key in event")
    return ""


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example filename:
    SAM_HANGINGPUB_Start_20260203.complete  -> SAM_HANGINGPUB_Start
    SAM_FICC_Start_20260203.complete        -> SAM_FICC_Start

    Rules:
    - remove .complete suffix
    - remove trailing _digits (timestamp)
    """
    print("[DEBUG] normalize input filename:", filename)

    name = filename
    if name.endswith(".complete"):
        name = name[:-len(".complete")]

    # remove trailing _digits (timestamp)
    name = re.sub(r"_[0-9]+$", "", name)

    print("[DEBUG] normalized mapping key:", name)
    return name


def extract_job_from_command(cmd: str) -> str:
    m = re.search(r"(?:\s|^)-(?:j|J)\s+([^\s]+)", cmd.strip() if cmd else "")
    return m.group(1) if m else ""


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ---- CONFIG ----
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/ADHOC_BUS_REQ/test_ybyo/"
    instance_id = "i-090e6f0a8fa26397"
    run_as_user = "gauhlk"

    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"

    mapping = load_job_mapping("autosys_job_mapping.json")

    s3_key_in_event = extract_s3_key_from_event(event)
    print(s3_key_in_event)

    if not s3_key_in_event:
        return {
            "ok": False,
            "error": "Could not extract S3 object key from event",
            "eventKeys": list(event.keys())
        }

    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        print("[ERROR] No mapping for key:", map_key)
        suggestions = [k for k in mapping.keys() if k in map_key or map_key in k]
        print("[DEBUG] suggestions:", suggestions)
        return {
            "ok": False,
            "error": "No mapping matched filename-derived key",
            "s3ObjectKey": s3_key_in_event,
            "filename": filename,
            "derivedKey": map_key,
            "availableKeys": list(mapping.keys())[:50],
            "suggestions": suggestions
        }

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job_from_json:", job_from_json)
    print("[DEBUG] cmd_from_json:", cmd_from_json)

    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    remote_script = f"""
set -e

JOB="{job_from_json}"

if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  LINE=$(autorep -J "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]][0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)

{cmd_from_json}
RC=$?

sleep 3
AFTER_TS=$(extract_last_start)

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_from_json}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"
""".strip()

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
    print("SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    evidence = s3_get_json_with_retry(bucket, s3_key, timeout_seconds=180, poll_seconds=3)

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
            started_confirmed = False
            reason = "Last Start did not increase (job may not have started or timestamp didn't change yet)"
    else:
        reason = "Missing before/after lastStart values in local evidence file. Check Autosys profile + autorep format."

    return {
        "ok": True,
        "autosysJobName": job_from_json,
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