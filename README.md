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

# -----------------------------
# Mapping (filename regex -> FULL sendevent command)
# -----------------------------
LOCAL_MAPPING_FILE = os.path.join(os.path.dirname(__file__), "autosys_job_mapping.json")
_autosys_cmd_map_cache = None  # cached dict {regex_pattern: "sendevent ... -j JOB"}


def _load_autosys_command_map() -> dict:
    """
    Loads mapping JSON from:
      1) S3 if env vars set: AUTOSYS_MAPPING_S3_BUCKET + AUTOSYS_MAPPING_S3_KEY
      2) local file autosys_job_mapping.json (packaged with Lambda)
    Caches for warm invocations.
    """
    global _autosys_cmd_map_cache
    if _autosys_cmd_map_cache is not None:
        return _autosys_cmd_map_cache

    s3_bucket = os.environ.get("AUTOSYS_MAPPING_S3_BUCKET", "").strip()
    s3_key = os.environ.get("AUTOSYS_MAPPING_S3_KEY", "").strip()

    if s3_bucket and s3_key:
        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            body = obj["Body"].read().decode("utf-8")
            mapping = json.loads(body)
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError("S3 mapping JSON is empty or not a dict")
            _autosys_cmd_map_cache = mapping
            print(f"Loaded Autosys mapping from S3: s3://{s3_bucket}/{s3_key} ({len(mapping)} rules)")
            return _autosys_cmd_map_cache
        except Exception as e:
            print(f"ERROR loading Autosys mapping from S3: s3://{s3_bucket}/{s3_key} -> {e}")
            raise

    # Local fallback
    try:
        with open(LOCAL_MAPPING_FILE, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Local mapping JSON is empty or not a dict")
        _autosys_cmd_map_cache = mapping
        print(f"Loaded Autosys mapping from local file: {LOCAL_MAPPING_FILE} ({len(mapping)} rules)")
        return _autosys_cmd_map_cache
    except Exception as e:
        print(f"ERROR loading Autosys mapping from local file: {LOCAL_MAPPING_FILE} -> {e}")
        raise


def resolve_autosys_command(object_key: str) -> str:
    """
    Finds the FULL Autosys command for the given S3 object key's filename.
    """
    mapping = _load_autosys_command_map()
    filename = (object_key or "").split("/")[-1].strip()

    if not filename:
        raise ValueError(f"Cannot resolve command: empty filename derived from key: {object_key}")

    for pattern, command in mapping.items():
        try:
            if re.match(pattern, filename):
                print(f"Autosys mapping matched. filename='{filename}' pattern='{pattern}' command='{command}'")
                return command
        except re.error as rex:
            raise ValueError(f"Invalid regex in mapping: '{pattern}' -> {rex}")

    raise ValueError(f"No Autosys command mapping found for filename: {filename} (key: {object_key})")


def extract_job_from_command(cmd: str) -> str:
    """
    Extracts job name from a sendevent command that includes: -j <JOBNAME>
    Example: sendevent -E FORCE_START_JOB -j GV7#SAM#box#HANGING_UPB_ADHOC_PROD
    """
    m = re.search(r"(?:^|\s)-j\s+([^\s]+)", cmd or "")
    if not m:
        raise ValueError(f"Cannot find '-j <JOB>' in command: {cmd}")
    return m.group(1).strip()


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\/#]", "_", s)


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
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


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    detail = event.get("detail") or {}
    req_params = (detail.get("requestParameters") or {})
    inbound_key = req_params.get("key") or ""
    print("Inbound key:", inbound_key)

    # --- Your current constants (keep as-is) ---
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo/"

    if not bucket:
        return {"ok": False, "error": "Missing evidence bucket. Set AUTOSYS_EVIDENCE_BUCKET env var."}

    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauh1k"
    document_name = (
        event.get("documentName")
        or detail.get("documentName")
        or "fundacntg-shellssmdoc-stepfunc"
    )

    if not instance_id:
        return {"ok": False, "error": "Missing instanceId"}

    # --- CHANGE: resolve FULL command from mapping file ---
    autosys_command = resolve_autosys_command(inbound_key)
    job_name = extract_job_from_command(autosys_command)

    print("Resolved autosys_command:", autosys_command)
    print("Extracted job_name:", job_name)

    # Evidence naming
    job_safe = sanitize(job_name)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    # Runs on EC2:
    # - BEFORE: autorep last start
    # - execute full autosys command (sendevent ...)
    # - AFTER: autorep last start
    # - save JSON locally and upload to S3
    remote_script = f"""
set -e

JOB="{job_name}"
AUTOSYS_CMD='{autosys_command}'

# Load Autosys profile if present
if [ -f /export/app1/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/app1/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  LINE=$(autorep -J "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)

# Run mapped command
eval "$AUTOSYS_CMD"
RC=$?

sleep 3
AFTER_TS=$(extract_last_start)

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_name}",
  "autosysCommand": "{autosys_command}".replace("\\\\","\\\\\\\\"),
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "commandRc": "$RC",
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
            "runAsUser": [run_as_user],
        },
        Comment="Autosys command executed + evidence saved locally and uploaded to S3"
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    # Read evidence JSON from S3
    evidence = s3_get_json_with_retry(bucket, s3_key, timeout_seconds=180, poll_seconds=3)

    before_ts = (evidence.get("lastStartBefore") or "").strip()
    after_ts = (evidence.get("lastStartAfter") or "").strip()

    autosys_ran_confirmed = False
    reason = None

    # --- CHANGE: confirm ran if before != after ---
    if before_ts and after_ts:
        try:
            dt_before = parse_mmddyyyy_hhmmss(before_ts)
            dt_after = parse_mmddyyyy_hhmmss(after_ts)
            if dt_after != dt_before:
                autosys_ran_confirmed = True
                reason = "Confirmed: last start time changed (before != after), Autosys job ran."
            else:
                reason = "Not confirmed: last start time did not change (before == after)."
        except Exception:
            # If parsing fails, still apply your rule strictly as string comparison
            if before_ts != after_ts:
                autosys_ran_confirmed = True
                reason = "Confirmed: before != after (string compare). Autosys job ran."
            else:
                reason = "Not confirmed: before == after (string compare)."
    else:
        reason = "Missing before/after lastStart values in evidence file. Check Autosys profile + autorep output."

    return {
        "ok": True,
        "inboundKey": inbound_key,
        "mappedAutosysCommand": autosys_command,
        "autosysJobNameExtracted": job_name,
        "autosysRanConfirmed": autosys_ran_confirmed,
        "autosysRunReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "commandRc": evidence.get("commandRc"),
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
    }




{
  "^SAM_HANGINGUPB_Start_.*\\.complete$": "sendevent -E FORCE_START_JOB -j GV7#SAM#box#HANGING_UPB_ADHOC_PROD",

  "^SAM_FICC_Start_.*\\.complete$": "sendevent -E FORCE_START_JOB -j GV7#SAM#box#FICC_GENCOST_ADHOC_PROD",

  "^SAM_GL_Extract_.*\\.complete$": "sendevent -E FORCE_START_JOB -j GV7#SAM#box#GLT_SEC_GL_ADHOC_PROD",

  "^SAM_GL_Publish_.*\\.complete$": "sendevent -E JOB_OFF_HOLD -j GV7#SAM#cmd#GLT_SEC_GL_START_ADHOC_PROD",

  "^SAM_GLCLOSE_SCD_.*\\.complete$": "sendevent -E FORCE_START_JOB -j GV7#SAM#box#SAM_GLCLOSE_SCD_ADHOC_PROD",

  "^SAM_EYTAXBUS_VEND_.*\\.complete$": "sendevent -E FORCE_START_JOB -j GV7#SAM#box#EY_TAXBUS_VEND_ADHOC_PROD"
}
