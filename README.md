import json
import time
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


# -------------------------
# Helpers (NO base64, safe with #)
# -------------------------
def sanitize(s: str) -> str:
    """
    Make a string safe for S3 keys / filenames.
    Keeps letters/digits/_-./ and replaces everything else with '-'.
    """
    if s is None:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")
    out = []
    for ch in str(s):
        out.append(ch if ch in allowed else "-")
    return "".join(out)


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3) -> dict:
    deadline = time.time() + timeout_seconds
    last_inv = None

    print(f"[DEBUG] wait_for_command: command_id={command_id} instance_id={instance_id} timeout={timeout_seconds}s poll={poll_seconds}s")

    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last_inv = inv
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code", "Unknown")
            print("[DEBUG] get_command_invocation error code:", code)
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        status = inv.get("Status")
        rc = inv.get("ResponseCode")
        print(f"[DEBUG] SSM invocation status={status} responseCode={rc}")

        if status in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last invocation: {last_inv}")


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3) -> dict:
    deadline = time.time() + timeout_seconds
    last_err = None

    print(f"[DEBUG] s3_get_json_with_retry: bucket={bucket} key={key} timeout={timeout_seconds}s poll={poll_seconds}s")

    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8")
            print("[DEBUG] Evidence JSON size:", len(body))
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = (e.response.get("Error") or {}).get("Code", "")
            print("[DEBUG] s3.get_object error code:", code)
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            print("[DEBUG] s3_get_json_with_retry generic exception:", repr(e))
            time.sleep(poll_seconds)

    raise TimeoutError(f"Evidence JSON not found in time s3://{bucket}/{key}. Last error: {last_err}")


def parse_mmddyyyy_hhmmss(s: str):
    # Example: 01/30/2026 02:41:11
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def load_job_mapping(filename: str = "autosys_job_mapping.json") -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    print("[DEBUG] Loading mapping file:", path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("[DEBUG] Mapping keys count:", len(data.keys()))
    print("[DEBUG] First 50 mapping keys:", list(data.keys())[:50])
    return data


def extract_s3_key_from_event(event: dict) -> str:
    """
    Supports EventBridge/CloudTrail style events.
    Prefer: detail.requestParameters.key
    Fallback: resources[].ARN for s3 object.
    """
    print("[DEBUG] extract_s3_key_from_event: event keys:", list(event.keys()))

    detail = event.get("detail") or {}
    req = detail.get("requestParameters") or {}
    key = req.get("key")

    if isinstance(key, str) and key.strip():
        print("[DEBUG] S3 key from detail.requestParameters.key:", key)
        return key

    resources = event.get("resources") or []
    for r in resources:
        arn = r.get("ARN") or r.get("arn") or ""
        # arn:aws:s3:::bucket/key...
        if isinstance(arn, str) and arn.startswith("arn:aws:s3:::") and "/" in arn:
            k = arn.split("arn:aws:s3:::")[-1]
            parts = k.split("/", 1)  # remove leading bucket/
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find s3 key in event")
    return ""


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example:
      SAM_HANGINGUPB_Start_20260203.complete  -> SAM_HANGINGUPB_Start
      SAM_FICC_Start_20260203.complete        -> SAM_FICC_Start

    Rules:
      - remove .complete suffix
      - remove trailing _digits (timestamp) WITHOUT regex
    """
    print("[DEBUG] normalize input filename:", filename)

    name = filename or ""
    if name.endswith(".complete"):
        name = name[: -len(".complete")]

    # remove trailing digits
    i = len(name) - 1
    while i >= 0 and name[i].isdigit():
        i -= 1
    name = name[: i + 1]

    # if ends with "_" after removing digits, remove that too
    if name.endswith("_"):
        name = name[:-1]

    print("[DEBUG] normalized mapping key:", name)
    return name


def extract_env_from_s3_key(s3_key: str) -> str:
    """
    Extract env from:
      .../OUT/DEVL1/.../filename
    """
    print("[DEBUG] Extracting ENV from s3_key:", s3_key)
    parts = (s3_key or "").split("/")
    for i, part in enumerate(parts):
        if part.upper() == "OUT" and i + 1 < len(parts):
            env = parts[i + 1]
            print("[DEBUG] Derived environment:", env)
            return env
    print("[WARN] Could not derive environment from S3 key")
    return ""


def apply_env_to_mapping(value: str, env: str) -> str:
    """
    Replace LOGENV placeholder with actual env.
    """
    if not value:
        return value
    before = value
    after = value.replace("LOGENV", env)
    print("[DEBUG] Before ENV replace:", before)
    print("[DEBUG] After  ENV replace:", after)
    return after


# -------------------------
# Lambda handler
# -------------------------
def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ---- CONFIG ----
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/ADHOC_BUS_REQ/test_ybyo/"
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"

    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"

    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] run_as_user:", run_as_user)
    print("[DEBUG] document_name:", document_name)

    # Load JSON mapping file packaged with lambda
    mapping = load_job_mapping("autosys_job_mapping.json")

    # Extract S3 object key from event
    s3_key_in_event = extract_s3_key_from_event(event)
    print("[DEBUG] s3_key_in_event:", s3_key_in_event)

    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract s3 object key from event", "eventKeys": list(event.keys())}

    # Extract ENV from path and replace LOGENV inside job_name/command
    env = extract_env_from_s3_key(s3_key_in_event)
    if not env:
        return {"ok": False, "error": "Could not extract environment from S3 key", "s3Key": s3_key_in_event}

    # Get filename and map key
    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        print("[ERROR] No mapping for key:", map_key)
        suggestions = [k for k in mapping.keys() if (k in map_key) or (map_key in k)]
        print("[DEBUG] suggestions:", suggestions)
        return {
            "ok": False,
            "error": "No mapping matched filename-derived key",
            "s3ObjectKey": s3_key_in_event,
            "filename": filename,
            "derivedKey": map_key,
            "availableKeys": list(mapping.keys())[:50],
            "suggestions": suggestions[:50],
        }

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))

    job_from_json_raw = (matched.get("job_name") or "").strip()
    cmd_from_json_raw = (matched.get("command") or "").strip()

    job_from_json = apply_env_to_mapping(job_from_json_raw, env)
    cmd_from_json = apply_env_to_mapping(cmd_from_json_raw, env)

    print("[DEBUG] job_from_json (final):", job_from_json)
    print("[DEBUG] cmd_from_json (final):", cmd_from_json)

    if not job_from_json:
        return {"ok": False, "error": "Mapped job_name is empty after env replacement", "mapKey": map_key}
    if not cmd_from_json:
        return {"ok": False, "error": "Mapped command is empty after env replacement", "mapKey": map_key}

    # Build evidence file location
    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))

    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] job_safe:", job_safe)
    print("[DEBUG] run_id:", run_id)
    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] evidence_s3_key:", evidence_s3_key)

    # Script runs on EC2 via SSM document:
    # - capture BEFORE lastStart
    # - run sendevent command (may include #)
    # - capture AFTER lastStart
    # - write evidence JSON locally
    # - upload to S3
    remote_script = f"""
set -e

JOB="{job_from_json}"

echo "[REMOTE] JOB=$JOB"
echo "[REMOTE] ENV={env}"
echo "[REMOTE] Evidence local file: {local_file}"
echo "[REMOTE] Evidence S3 location: s3://{bucket}/{evidence_s3_key}"

# Load Autosys profile if present (adjust path if needed)
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  echo "[REMOTE] Sourcing Autosys profile..."
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
else
  echo "[REMOTE] Autosys profile not found at expected path (continuing)."
fi

extract_last_start() {{
  # Pull first matching job line, then extract MM/DD/YYYY HH:MM:SS
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "[REMOTE] autorep first line: $LINE"
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)
echo "[REMOTE] BEFORE_TS=$BEFORE_TS"

echo "[REMOTE] Running command now..."
{cmd_from_json}
RC=$?
echo "[REMOTE] sendevent RC=$RC"

sleep 3

AFTER_TS=$(extract_last_start)
echo "[REMOTE] AFTER_TS=$AFTER_TS"

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_from_json}",
  "environment": "{env}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

echo "[REMOTE] Evidence file written: {local_file}"
echo "[REMOTE] Uploading evidence to S3..."
aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}"
echo "[REMOTE] Evidence uploaded."
""".strip()

    print("[DEBUG] remote_script (first 800 chars):", remote_script[:800])
    print("[DEBUG] remote_script (last 800 chars):", remote_script[-800:])

    # Send to SSM
    try:
        resp = ssm.send_command(
            DocumentName=document_name,
            InstanceIds=[instance_id],
            Parameters={
                "command": [remote_script],
                "runAsUser": [run_as_user],
            },
            Comment="Autosys trigger + evidence saved locally and uploaded to S3",
        )
    except ClientError as e:
        print("[ERROR] ssm.send_command failed:", repr(e))
        raise

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)

    # Wait for command completion (SSM success/fail != autosys start confirmation)
    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("[DEBUG] Final SSM status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    # Read evidence JSON from S3 (NOT stdout/stderr, NOT Parameter Store)
    evidence = s3_get_json_with_retry(bucket, evidence_s3_key, timeout_seconds=180, poll_seconds=3)
    print("[DEBUG] evidence JSON:", json.dumps(evidence, indent=2))

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
                reason = "Last Start did not increase (job may not have started yet or timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps: {repr(e)}"
    else:
        reason = "Missing before/after lastStart values in evidence file. Check Autosys profile + autorep output format."

    return {
        "ok": True,
        "s3ObjectKey": s3_key_in_event,
        "environment": env,
        "mappingKey": map_key,
        "autosysJobName": job_from_json,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendeventRc": evidence.get("sendeventRc"),
        "evidenceLocation": {
            "localFileOnInstance": local_file,
            "s3Bucket": bucket,
            "s3Key": evidence_s3_key,
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