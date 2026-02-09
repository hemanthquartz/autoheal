import json
import time
import re
from datetime import datetime
import os

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\/]", "_", s or "")


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_inv = None
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last_inv = inv
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last: {last_inv}")


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3):
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
    # expects JSON file to be packaged next to this python file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_trigger_text(event: dict) -> str:
    """
    Choose the text that your regex patterns should match.
    You can adjust this if your event has a known field.
    """
    detail = event.get("detail") or {}

    # Try common candidates first
    for key in ("alert_name", "alertName", "name", "message", "title", "eventName", "jobEvent", "summary"):
        v = detail.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # If you already have some explicit field passed
    for key in ("trigger", "triggerText", "jobKey", "jobEvent"):
        v = event.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # Fallback: stringify detail
    try:
        return json.dumps(detail, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return str(detail)


def match_mapping(trigger_text: str, mapping: dict) -> tuple[str, dict]:
    """
    mapping keys are regex patterns. values contain:
      - job_name (Autosys job)
      - command (full sendevent command)
    Returns: (matched_pattern, matched_value)
    """
    for pattern, val in mapping.items():
        try:
            if re.search(pattern, trigger_text):
                return pattern, val
        except re.error:
            # skip invalid regex patterns safely
            continue
    return "", {}


def extract_job_from_command(cmd: str) -> str:
    """
    Supports -J or -j.
    Example: sendevent ... -j GV7#...
    """
    if not cmd:
        return ""
    m = re.search(r"(?:^|\s)-(?:J|j)\s+([^\s]+)", cmd.strip())
    return m.group(1) if m else ""


def bash_single_quote(s: str) -> str:
    """
    Safe for bash single-quoted literal even if s contains #, spaces, $, ", etc.
    """
    if s is None:
        s = ""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ===== YOUR CONFIG =====
    bucket = "fundacntg-devl-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo/"
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"
    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"

    if not bucket:
        return {"ok": False, "error": "Missing evidence bucket."}

    # ===== Load mapping JSON =====
    try:
        mapping = load_job_mapping("autosys_job_mapping.json")
        print(f"Loaded mapping entries: {len(mapping)}")
    except Exception as e:
        return {"ok": False, "error": f"Failed to load autosys_job_mapping.json: {e}"}

    trigger_text = pick_trigger_text(event)
    print("Trigger text used for regex match:", trigger_text)

    matched_pattern, matched = match_mapping(trigger_text, mapping)

    if not matched:
        return {
            "ok": False,
            "error": "No mapping matched trigger text",
            "triggerText": trigger_text,
        }

    # JSON can contain either:
    #   job_name: Autosys job
    #   command: full sendevent command
    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    # If someone stored full command into job_name and left command blank, still handle it:
    if not cmd_from_json and job_from_json:
        # treat job_name as full command
        cmd_from_json = job_from_json

    # Ensure JOB is an Autosys job name (for autorep evidence)
    if not job_from_json and cmd_from_json:
        job_from_json = extract_job_from_command(cmd_from_json)

    if not job_from_json or not cmd_from_json:
        return {
            "ok": False,
            "error": "Mapping found but missing job_name/command",
            "matchedPattern": matched_pattern,
            "matchedValue": matched,
        }

    # Evidence paths
    job_safe = sanitize(job_from_json)  # use actual autosys job name for evidence grouping
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    # Quote-safe literals for bash (handles #)
    job_literal = bash_single_quote(job_from_json)
    cmd_literal = bash_single_quote(cmd_from_json)

    # Remote script (run under bash explicitly)
    remote_script = f"""bash -s <<'EOS'
set -e

JOB={job_literal}
CMD={cmd_literal}

echo "=== JOB from JSON ==="
echo "$JOB"
echo "=== CMD from JSON ==="
echo "$CMD"
echo "====================="

# Load Autosys profile if present
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "autorep line: $LINE"
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

echo "--- BEFORE ---"
BEFORE_TS=$(extract_last_start)
echo "BEFORE_TS=$BEFORE_TS"

echo "--- RUN CMD ---"
set +e
OUT="$(bash -lc "$CMD" 2>&1)"
RC=$?
set -e
echo "CMD_RC=$RC"
echo "CMD_OUTPUT_BEGIN"
echo "$OUT"
echo "CMD_OUTPUT_END"

sleep 3

echo "--- AFTER ---"
AFTER_TS=$(extract_last_start)
echo "AFTER_TS=$AFTER_TS"

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "$JOB",
  "command": "$(echo "$CMD" | tr '\\n' ' ')",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendEventRC": "$RC",
  "commandOutput": "$(printf "%s" "$OUT" | tr '\\n' ' ' | sed 's/"/\\\\\\"/g')",
  "capturedAtUtc": "$NOW_ISO"
}}
EOF

echo "Wrote evidence file: {local_file}"
aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"
echo "Uploaded evidence to s3://{bucket}/{s3_key}"
EOS
""".strip()

    # Send to SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger via mapping JSON + evidence saved locally and uploaded to S3",
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
        reason = "Missing before/after lastStart values in evidence. Check commandOutput."

    return {
        "ok": True,
        "matchedPattern": matched_pattern,
        "triggerText": trigger_text,
        "autosysJobName": job_from_json,          # JOB from JSON
        "autosysCommand": cmd_from_json,          # CMD from JSON
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendEventRC": evidence.get("sendEventRC"),
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
        "commandOutput": evidence.get("commandOutput"),
    }