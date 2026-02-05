{
  "^SAM_HANGINGUPB_Start_.*\\.complete$": "GV7/SAM#boxHANGING_UP_ADHOC_PROD",

  "^SAM_GL_Extract_.*\\.complete$": "GV7/SAM#boxGL_SEC_GL_ADHOC_PROD",

  "^SAM_GL_Publish_.*\\.complete$": "GV7/SAM#boxGL_SEC_GL_ADHOC_PROD",

  "^SAM_FICC_Start_.*\\.complete$": "GV7/SAM#boxFICC_GENCOST_ADHOC_PROD",

  "^SAM_EYTAXBUS_Vend_.*\\.complete$": "GV7/SAM#boxEYTAXBUS_VEND_ADHOC_PROD",

  "^TA_PRCECON_Start_.*\\.complete$": "GV7/TA#boxTADS_PRC_Recon_PROD",

  "^TA_Rateupdate_Start_.*\\.complete$": "GV7/TA#boxTA_EOP_Rerun_ADHOC_DEL_PROD",

  "^TA_HDGRCL_Extract_.*\\.complete$": "GV7/TA#boxTADS_PRISM_EOM_B01_ADHOC_PROD",

  "^TA_GL_Extract_.*\\.complete$": "GV7/TA#boxTADS_GL_EOM_B01_ADHOC_PROD",

  "^TA_GL_Publish_.*\\.complete$": "GV7/TA#boxTA_GL_ALL_START_B01_ADHC_PROD"
}




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
# Autosys mapping (EXTERNAL FILE)
# -----------------------------
# Option A (preferred): Load from S3 if env vars are set
#   AUTOSYS_MAPPING_S3_BUCKET=<bucket>
#   AUTOSYS_MAPPING_S3_KEY=<key/to/autosys_job_mapping.json>
#
# Option B: Load from local file packaged with the Lambda zip:
#   autosys_job_mapping.json (same folder as this .py)
#
LOCAL_MAPPING_FILE = os.path.join(os.path.dirname(__file__), "autosys_job_mapping.json")

_autosys_job_map_cache = None  # cached dict {regex_pattern: job_name}


def _load_autosys_job_map() -> dict:
    """
    Loads filename-regex -> Autosys job mapping from:
      1) S3 (if AUTOSYS_MAPPING_S3_BUCKET & AUTOSYS_MAPPING_S3_KEY set), else
      2) local file autosys_job_mapping.json packaged with Lambda
    Caches result for warm invocations.
    """
    global _autosys_job_map_cache
    if _autosys_job_map_cache is not None:
        return _autosys_job_map_cache

    s3_bucket = os.environ.get("AUTOSYS_MAPPING_S3_BUCKET", "").strip()
    s3_key = os.environ.get("AUTOSYS_MAPPING_S3_KEY", "").strip()

    if s3_bucket and s3_key:
        # Load mapping from S3
        try:
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
            body = obj["Body"].read().decode("utf-8")
            mapping = json.loads(body)
            if not isinstance(mapping, dict) or not mapping:
                raise ValueError("S3 mapping JSON is empty or not a dict")
            _autosys_job_map_cache = mapping
            print(f"Loaded Autosys mapping from S3: s3://{s3_bucket}/{s3_key} ({len(mapping)} rules)")
            return _autosys_job_map_cache
        except Exception as e:
            print(f"ERROR loading Autosys mapping from S3: s3://{s3_bucket}/{s3_key} -> {e}")
            raise

    # Load mapping from local file
    try:
        with open(LOCAL_MAPPING_FILE, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("Local mapping JSON is empty or not a dict")
        _autosys_job_map_cache = mapping
        print(f"Loaded Autosys mapping from local file: {LOCAL_MAPPING_FILE} ({len(mapping)} rules)")
        return _autosys_job_map_cache
    except Exception as e:
        print(f"ERROR loading Autosys mapping from local file: {LOCAL_MAPPING_FILE} -> {e}")
        raise


def resolve_autosys_job(object_key: str) -> str:
    """
    Resolves Autosys job name based on the *filename* in the S3 object key.
    Uses regex patterns from the external mapping JSON.
    """
    mapping = _load_autosys_job_map()
    filename = (object_key or "").split("/")[-1].strip()

    if not filename:
        raise ValueError(f"Cannot resolve job: empty filename derived from key: {object_key}")

    for pattern, job in mapping.items():
        try:
            if re.match(pattern, filename):
                print(f"Autosys mapping matched. filename='{filename}' pattern='{pattern}' job='{job}'")
                return job
        except re.error as rex:
            raise ValueError(f"Invalid regex in mapping: '{pattern}' -> {rex}")

    raise ValueError(f"No Autosys job mapping found for filename: {filename} (key: {object_key})")


# -----------------------------
# Existing helpers (from your Lambda)
# -----------------------------
def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\/]", "_", s)


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


# -----------------------------
# Lambda handler
# -----------------------------
def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # Expecting S3 event via EventBridge (your screenshot pattern)
    detail = event.get("detail") or {}
    req_params = (detail.get("requestParameters") or {})
    inbound_key = req_params.get("key") or ""

    print("Inbound key:", inbound_key)

    # ---- YOUR CURRENT CONSTANTS (as in screenshot) ----
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo/"

    if not bucket:
        return {"ok": False, "error": "Missing evidence bucket. Set AUTOSYS_EVIDENCE_BUCKET env var."}

    # ---- YOUR CURRENT SSM TARGETS (as in screenshot; keep same unless you change) ----
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauh1k"
    document_name = (
        event.get("documentName")
        or detail.get("documentName")
        or "fundacntg-shellssmdoc-stepfunc"
    )

    # ---- CHANGE #1: job_name resolved dynamically from external mapping file ----
    job_name = resolve_autosys_job(inbound_key)
    if not instance_id or not job_name:
        return {"ok": False, "error": "Missing instanceId or jobName"}

    # Evidence file naming
    job_safe = sanitize(job_name)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("Resolved job_name:", job_name)
    print("Evidence local_file:", local_file)
    print("Evidence s3_key:", s3_key)
    print("SSM target instance:", instance_id, "document:", document_name, "runAs:", run_as_user)

    # Runs on EC2: collect BEFORE, run sendevent, collect AFTER, save to LOCAL FILE, upload to S3
    remote_script = f"""
set -e

JOB="{job_name}"

# Load Autosys profile if present (adjust path if needed)
if [ -f /export/app1/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/app1/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  # Pull first matching job line, then extract MM/DD/YYYY HH:MM:SS
  LINE=$(autorep -J "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)

sendevent -E FORCE_STARTJOB -J "$JOB"
RC=$?

sleep 3
AFTER_TS=$(extract_last_start)

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_name}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"
""".strip()

    # Send to SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger + evidence saved locally and uploaded to S3"
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    # Read evidence JSON from S3 (NOT stdout/stderr, NOT Parameter Store)
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
            reason = "Last Start did not increase (job may not have started or timestamp didn't change yet)"
    else:
        reason = "Missing before/after lastStart values in local evidence file. Check Autosys profile + autorep format."

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