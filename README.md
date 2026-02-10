import json
import time
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    """
    Make a safe-ish string for filenames/keys without regex.
    Keep: letters, digits, '-', '_', '.', '/'
    Replace everything else with '-'
    """
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.//")
    out = []
    for ch in (s or ""):
        out.append(ch if ch in allowed else "-")
    return "".join(out)


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except ClientError as e:
            code = (e.response.get("Error", {}) or {}).get("Code", "Unknown")
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}")


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
            code = (e.response.get("Error", {}) or {}).get("Code", "")
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
    print("[DEBUG] Mapping keys count:", len(list(data.keys())))
    print("[DEBUG] Sample keys:", list(data.keys())[:10])
    return data


def extract_s3_key_from_event(event: dict) -> str:
    """
    Supports EventBridge/CloudTrail style events.
    Prefer: event.detail.requestParameters.key
    Fallback: event.resources[].ARN (arn:aws:s3:::bucket/key...)
    """
    detail = event.get("detail") or {}
    req = detail.get("requestParameters") or {}
    key = req.get("key")

    if isinstance(key, str) and key.strip():
        print("[DEBUG] S3 key from detail.requestParameters.key:", key)
        return key

    resources = event.get("resources") or []
    for r in resources:
        arn = r.get("ARN") or r.get("arn") or ""
        if isinstance(arn, str) and arn.startswith("arn:aws:s3:::") and "/" in arn:
            # arn:aws:s3:::bucket/key...
            k = arn.split("arn:aws:s3:::")[-1]
            parts = k.split("/", 1)
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find S3 key in event")
    return ""


def extract_env_from_s3_key(s3_key: str) -> str:
    """
    Extract environment from S3 path.
    Expected pattern:
    .../OUT/<ENV>/SCD/...
    """
    print("[DEBUG] Extracting env from s3 key:", s3_key)
    parts = (s3_key or "").split("/")
    for i, part in enumerate(parts):
        if part == "OUT" and i + 1 < len(parts):
            env = parts[i + 1]
            print("[DEBUG] Extracted environment:", env)
            return env
    raise ValueError(f"Could not extract environment from s3 key: {s3_key}")


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example filename:
      SAM_HANGINGUPB_Start_20260203.complete  -> SAM_HANGINGUPB_Start
      SAM_FICC_Start_20260203.complete       -> SAM_FICC_Start

    Rules (NO regex):
      - remove .complete suffix
      - if last token after '_' is all digits -> remove that trailing _<digits>
    """
    print("[DEBUG] normalize input filename:", filename)
    name = (filename or "").strip()

    if name.endswith(".complete"):
        name = name[: -len(".complete")]

    # Remove trailing _<digits> (timestamp) if present
    if "_" in name:
        head, tail = name.rsplit("_", 1)
        if tail.isdigit():
            name = head

    print("[DEBUG] normalized mapping key:", name)
    return name


def apply_env_to_mapping(entry: dict, env: str) -> dict:
    """
    Replace LOGENV with actual environment in job_name and command.
    """
    updated = {}
    for k, v in (entry or {}).items():
        if isinstance(v, str):
            updated[k] = v.replace("LOGENV", env)
        else:
            updated[k] = v
    print("[DEBUG] Mapping after env replacement:", json.dumps(updated, indent=2))
    return updated


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ---- CONFIG (prefer env vars, fall back to your current values) ----
    bucket = os.environ.get("EVIDENCE_BUCKET", "fundacntg-dev1-ftbu-us-east-1")
    prefix = os.environ.get("EVIDENCE_PREFIX", "prepare/cin/dflt/ADHOC_BUS_REQ/test_ybyo/")
    instance_id = os.environ.get("TARGET_INSTANCE_ID", "i-090e6f0a08fa26397")
    run_as_user = os.environ.get("RUN_AS_USER", "gauhlk")

    detail = event.get("detail") or {}
    document_name = (
        event.get("documentName")
        or detail.get("documentName")
        or os.environ.get("SSM_DOCUMENT_NAME", "fundacntg-shellssmdoc-stepfunc")
    )

    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] run_as_user:", run_as_user)
    print("[DEBUG] document_name:", document_name)

    # Load mapping JSON from Lambda package
    mapping = load_job_mapping("autosys_job_mapping.json")

    # Extract S3 key from event
    s3_key_in_event = extract_s3_key_from_event(event)
    print("[DEBUG] s3_key_in_event:", s3_key_in_event)
    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract s3 object key from event", "eventKeys": list(event.keys())}

    # Extract ENV from S3 key (OUT/<ENV>/...)
    env = extract_env_from_s3_key(s3_key_in_event)

    # Derive mapping key from filename
    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        print("[ERROR] No mapping for key:", map_key)
        suggestions = [k for k in mapping.keys() if (k in map_key or map_key in k)]
        print("[DEBUG] suggestions:", suggestions)
        return {
            "ok": False,
            "error": "No mapping matched filename-derived key",
            "s3ObjectKey": s3_key_in_event,
            "filename": filename,
            "derivedKey": map_key,
            "availableKeysSample": list(mapping.keys())[:50],
            "suggestions": suggestions,
        }

    # Apply env replacement (LOGENV -> env) inside job_name and command
    matched = apply_env_to_mapping(matched, env)

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job_from_json:", job_from_json)
    print("[DEBUG] cmd_from_json:", cmd_from_json)

    if not job_from_json or not cmd_from_json:
        return {
            "ok": False,
            "error": "Mapped entry missing job_name or command after env replacement",
            "matched": matched,
            "derivedKey": map_key,
        }

    # Evidence file/key
    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] job_safe:", job_safe)
    print("[DEBUG] run_id:", run_id)
    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] evidence_s3_key:", evidence_s3_key)

    # Remote script executed on EC2 via SSM.
    # - Collect BEFORE last start time
    # - Run sendevent (cmd_from_json)
    # - Collect AFTER last start time
    # - Write evidence JSON locally on instance
    # - Upload evidence JSON to S3
    #
    # NOTE: Autosys profile path uses the extracted env (e.g., DEVL1)
    remote_script = f"""
set -e

JOB="{job_from_json}"

echo "[REMOTE] Using JOB=$JOB"
echo "[REMOTE] Using ENV={env}"

# Load Autosys profile if present (adjust path if needed)
PROFILE="/export/appl/gv7/gv7dev1/src/{env}/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  echo "[REMOTE] Sourcing profile: $PROFILE"
  source "$PROFILE"
else
  echo "[REMOTE] Profile not found: $PROFILE"
fi

extract_last_start() {{
  # Pull first matching job line, then extract MM/DD/YYYY HH:MM:SS
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  if [ -z "$LINE" ]; then
    echo ""
    return 0
  fi

  # Find first token that looks like MM/DD/YYYY and next token HH:MM:SS
  # (NO regex) - split by spaces and scan
  TS=""
  PREV=""
  for tok in $LINE; do
    # If previous token has '/' and current token has ':' then combine
    if echo "$PREV" | grep -q "/" && echo "$tok" | grep -q ":"; then
      TS="$PREV $tok"
      break
    fi
    PREV="$tok"
  done
  echo "$TS"
}}

BEFORE_TS=$(extract_last_start)
echo "[REMOTE] BEFORE_TS=$BEFORE_TS"

echo "[REMOTE] Running command: {cmd_from_json}"
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
  "envFromS3Path": "{env}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

echo "[REMOTE] Evidence written to {local_file}"
echo "[REMOTE] Uploading evidence to s3://{bucket}/{evidence_s3_key}"
aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}"
echo "[REMOTE] Upload complete"
""".strip()

    print("[DEBUG] remote_script length:", len(remote_script))
    print("[DEBUG] Sending command to SSM...")

    # Send to SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger + evidence saved locally and uploaded to S3",
    )

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("[DEBUG] SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    # Read evidence JSON from S3 (NOT stdout/stderr, NOT Parameter Store)
    print("[DEBUG] Reading evidence JSON from S3...")
    evidence = s3_get_json_with_retry(bucket, evidence_s3_key, timeout_seconds=180, poll_seconds=3)
    print("[DEBUG] evidence:", json.dumps(evidence, indent=2))

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
                reason = "Last Start did not increase (job may not have started yet or timestamp didn't change)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps: {e}"
    else:
        reason = "Missing before/after lastStart values in evidence file. Check autosys profile + autorep output."

    return {
        "ok": True,
        "s3EventObjectKey": s3_key_in_event,
        "envExtractedFromPath": env,
        "derivedMappingKey": map_key,
        "autosysJobName": job_from_json,
        "autosysCommand": cmd_from_json,
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