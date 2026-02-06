# index.py
import os
import json
import time
import re
from datetime import datetime
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\/\.]", "_", s or "")


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3) -> dict:
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


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3) -> dict:
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


def load_autosys_mapping() -> dict:
    """
    autosys_job_mapping.json must be packaged alongside this index.py
    """
    here = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(here, "autosys_job_mapping.json")
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"autosys_job_mapping.json not found at {mapping_path}")
    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not data:
        raise ValueError("autosys_job_mapping.json must be a non-empty JSON object of {pattern: command}")
    return data


def pick_autosys_command(inbound_key: str, mapping: dict) -> str | None:
    """
    Matches mapping patterns (regex) to the inbound filename first, then full key.
    Your patterns look like: ^SAM_..._Start_.*\\.complete$
    """
    filename = os.path.basename(inbound_key or "")

    # 1) filename first (most common)
    for pattern, cmd in mapping.items():
        try:
            if re.search(pattern, filename):
                return cmd
        except re.error:
            # bad regex pattern in mapping - skip so lambda doesn't crash
            continue

    # 2) fallback full key
    for pattern, cmd in mapping.items():
        try:
            if re.search(pattern, inbound_key or ""):
                return cmd
        except re.error:
            continue

    return None


def extract_job_name_from_command(cmd: str) -> str | None:
    """
    Tries to pull the Autosys job name from a sendevent command:
      sendevent -E FORCE_START_JOB -j GV7#SAM#box#HANGING_UPB_ADHOC_DEVL1
    """
    m = re.search(r"(?:^|\s)-j\s+([^\s]+)", cmd or "")
    if m:
        return m.group(1).strip()
    return None


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # Expecting S3 event via EventBridge
    detail = event.get("detail") or {}
    req_params = (detail.get("requestParameters") or {})
    inbound_key = req_params.get("key") or ""

    # If key is URL-encoded (common), decode it
    inbound_key = unquote_plus(inbound_key)

    print("Inbound key:", inbound_key)

    if not inbound_key:
        return {
            "ok": False,
            "error": "Missing inbound S3 key in event.detail.requestParameters.key",
        }

    # ---- Load mapping and derive the correct command from file name ----
    mapping = load_autosys_mapping()
    autosys_cmd = pick_autosys_command(inbound_key, mapping)

    if not autosys_cmd:
        return {
            "ok": False,
            "error": "No matching autosys command for inbound file",
            "inboundKey": inbound_key,
            "filename": os.path.basename(inbound_key),
            "hint": "Update autosys_job_mapping.json regex patterns to match the inbound filename/key.",
        }

    print("Matched autosys command:", autosys_cmd)

    # Optional: extract job name (used only for BEFORE/AFTER last start evidence)
    job_name = extract_job_name_from_command(autosys_cmd)
    print("Extracted job name:", job_name)

    # ---- Config (use env vars; defaults shown) ----
    evidence_bucket = os.environ.get("AUTOSYS_EVIDENCE_BUCKET", "").strip()
    evidence_prefix = os.environ.get("AUTOSYS_EVIDENCE_PREFIX", "prepare/cin/dflt/SAM/test_ybyo/").strip()

    instance_id = os.environ.get("AUTOSYS_TARGET_INSTANCE_ID", "").strip()  # REQUIRED
    run_as_user = os.environ.get("AUTOSYS_RUN_AS_USER", "gauhlk").strip()
    document_name = os.environ.get("AUTOSYS_SSM_DOCUMENT", "fundacntg-shellssmdoc-stepfunc").strip()

    ssm_timeout_seconds = int(os.environ.get("AUTOSYS_SSM_TIMEOUT_SECONDS", "900").strip())
    ssm_poll_seconds = int(os.environ.get("AUTOSYS_SSM_POLL_SECONDS", "3").strip())

    evidence_timeout_seconds = int(os.environ.get("AUTOSYS_EVIDENCE_TIMEOUT_SECONDS", "180").strip())
    evidence_poll_seconds = int(os.environ.get("AUTOSYS_EVIDENCE_POLL_SECONDS", "3").strip())

    if not evidence_bucket:
        return {"ok": False, "error": "Missing evidence bucket. Set AUTOSYS_EVIDENCE_BUCKET env var."}
    if not instance_id:
        return {"ok": False, "error": "Missing target instance. Set AUTOSYS_TARGET_INSTANCE_ID env var."}
    if not document_name:
        return {"ok": False, "error": "Missing SSM document. Set AUTOSYS_SSM_DOCUMENT env var."}

    # Evidence file naming based on inbound filename
    filename = os.path.basename(inbound_key)
    file_tag = sanitize(filename)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{file_tag}_{run_id}.json"
    s3_key = f"{evidence_prefix.rstrip('/')}/{file_tag}/{run_id}.json"

    # ---------------- Remote script ----------------
    # IMPORTANT:
    # - Triggers based on mapped command (autosys_cmd)
    # - Captures BEFORE/AFTER lastStart for that job (if job_name extracted)
    # - Writes evidence to LOCAL FILE and uploads to S3 (NOT stdout/stderr, NOT Parameter Store)
    #
    # Note: We escape quotes inside autosys_cmd for JSON safety.
    autosys_cmd_escaped = autosys_cmd.replace('"', '\\"')
    job_name_safe = (job_name or "").replace('"', '\\"')

    remote_script = f"""#!/bin/bash
set -e

# Load Autosys profile if present (adjust path if needed)
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/gv7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/gv7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

JOB="{job_name_safe}"

extract_last_start() {{
  if [ -z "$JOB" ]; then
    echo ""
    return 0
  fi

  # Try to find MM/DD/YYYY HH:MM:SS from autorep output
  LINE=$(autorep -j "$JOB" 2>/dev/null | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)

# Trigger job (command comes from autosys_job_mapping.json)
{autosys_cmd}
RC=$?

sleep 3

AFTER_TS=$(extract_last_start)

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "inboundKey": "{inbound_key}",
  "filename": "{filename}",
  "autosysCommand": "{autosys_cmd_escaped}",
  "jobName": "$JOB",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{evidence_bucket}/{s3_key}"
"""

    # ---------------- Send to SSM ----------------
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger derived from inbound file name; evidence saved locally and uploaded to S3",
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_for_command(
        command_id,
        instance_id,
        timeout_seconds=ssm_timeout_seconds,
        poll_seconds=ssm_poll_seconds,
    )

    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    # ---------------- Read evidence JSON from S3 ----------------
    evidence = s3_get_json_with_retry(
        evidence_bucket,
        s3_key,
        timeout_seconds=evidence_timeout_seconds,
        poll_seconds=evidence_poll_seconds,
    )

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
                reason = "Last Start increased after sendevent (strong confirmation job started)"
            else:
                started_confirmed = False
                reason = "Last Start did not increase (job may not have started yet OR timestamp didn’t change)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps: {e}"
    else:
        reason = "Missing before/after lastStart values in evidence. Check autorep output format and jobName extraction."

    return {
        "ok": True,
        "inboundKey": inbound_key,
        "filename": filename,
        "matchedAutosysCommand": autosys_cmd,
        "extractedJobName": job_name,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendeventRc": evidence.get("sendeventRc"),
        "evidenceLocation": {
            "localFileOnInstance": local_file,
            "s3Bucket": evidence_bucket,
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