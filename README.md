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
    # keep it simple and safe for S3 key paths
    # allow letters, digits, _, -, ., /
    out = []
    for ch in (s or ""):
        if ch.isalnum() or ch in ["_", "-", ".", "/"]:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code", "Unknown")
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
            code = (e.response.get("Error") or {}).get("Code", "")
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
        arn = r.get("ARN") or r.get("arn") or ""
        if isinstance(arn, str) and arn.startswith("arn:aws:s3:::") and "/" in arn:
            # arn:aws:s3:::bucket/key...
            k = arn.split("arn:aws:s3:::", 1)[-1]
            parts = k.split("/", 1)
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find s3 key in event")
    return ""


def extract_env_from_s3_key(s3_key: str) -> str:
    """
    Your path pattern:
      .../OUT/DEVL1/...

    Extract env as the segment right after 'OUT'.
    """
    parts = [p for p in (s3_key or "").split("/") if p]
    print("[DEBUG] s3_key parts:", parts)

    # Find 'OUT' (case-sensitive to match your folder)
    for i, p in enumerate(parts):
        if p == "OUT":
            if i + 1 < len(parts):
                env = parts[i + 1]
                print("[DEBUG] Extracted env from OUT/<env>:", env)
                return env
            break

    print("[DEBUG] Could not extract env (OUT not found or missing next segment)")
    return ""


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example filename:
      SAM_HANGINGUPB_Start_20260203.complete  ->  SAM_HANGINGUPB_Start

    Rules:
    - remove .complete suffix
    - remove trailing _digits (timestamp)
    - NO regex: only split/loop checks
    """
    print("[DEBUG] normalize input filename:", filename)
    name = filename or ""

    if name.endswith(".complete"):
        name = name[: -len(".complete")]

    # remove trailing _digits (example: _20260203)
    # walk backwards while digits, then if preceding char is '_' remove that too.
    i = len(name) - 1
    while i >= 0 and name[i].isdigit():
        i -= 1

    # if we removed at least one digit and now we're at '_' -> cut there
    if i < len(name) - 1 and i >= 0 and name[i] == "_":
        name = name[:i]

    print("[DEBUG] normalized mapping key:", name)
    return name


def apply_env_replacements(text: str, env: str) -> str:
    if not isinstance(text, str):
        return text
    if not env:
        return text
    # Replace the literal token LOGENV
    return text.replace("LOGENV", env)


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ---------- CONFIG (keep your existing values here) ----------
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/ADHOC_BUS_REQ/test_ybyo/"  # used only for evidence upload location
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"

    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"
    # ------------------------------------------------------------

    mapping = load_job_mapping("autosys_job_mapping.json")

    s3_key_in_event = extract_s3_key_from_event(event)
    print("[DEBUG] s3_key_in_event:", s3_key_in_event)

    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract s3 object key from event", "eventKeys": list(event.keys())}

    # 1) Extract env from S3 path
    env_value = extract_env_from_s3_key(s3_key_in_event)
    print("[DEBUG] env_value:", env_value)

    # 2) Extract filename and map to mapping key
    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        print("[ERROR] No mapping for key:", map_key)
        suggestions = []
        # simple "contains" suggestion (no regex)
        for k in mapping.keys():
            if k in map_key or map_key in k:
                suggestions.append(k)

        return {
            "ok": False,
            "error": "No mapping matched filename-derived key",
            "s3ObjectKey": s3_key_in_event,
            "filename": filename,
            "derivedKey": map_key,
            "availableKeysSample": list(mapping.keys())[:50],
            "suggestions": suggestions[:50],
        }

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))

    # 3) Replace LOGENV in json values using extracted env
    job_from_json_raw = (matched.get("job_name") or "").strip()
    cmd_from_json_raw = (matched.get("command") or "").strip()

    job_from_json = apply_env_replacements(job_from_json_raw, env_value)
    cmd_from_json = apply_env_replacements(cmd_from_json_raw, env_value)

    print("[DEBUG] job_from_json_raw:", job_from_json_raw)
    print("[DEBUG] cmd_from_json_raw:", cmd_from_json_raw)
    print("[DEBUG] env-applied job_from_json:", job_from_json)
    print("[DEBUG] env-applied cmd_from_json:", cmd_from_json)

    # If your mapping has only command and job_name is optional, keep going anyway
    job_safe = sanitize(job_from_json if job_from_json else map_key)
    run_id = str(int(time.time()))

    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    # Remote script:
    # - loads autosys profile
    # - captures last start BEFORE and AFTER
    # - runs command safely even if it includes '#'
    # - writes evidence JSON locally and uploads to S3
    remote_script = f"""
set -e

JOB="{job_from_json}"
CMD="{cmd_from_json}"

echo "[DEBUG] JOB=$JOB"
echo "[DEBUG] CMD=$CMD"

# Load Autosys profile if present (adjust path if needed)
if [ -f /export/appl/gv7/gv7dev1/src/{env_value}/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/{env_value}/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  # Pull first line that includes job, then extract MM/DD/YYYY HH:MM:SS (best-effort)
  LINE=$(autorep -J "$JOB" 2>/dev/null | head -n 1 || true)
  echo "[DEBUG] autorep first line: $LINE"
  # Keep your existing grep extraction (works in your environment)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

BEFORE_TS=$(extract_last_start)
echo "[DEBUG] BEFORE_TS=$BEFORE_TS"

echo "[DEBUG] Running command via bash -lc to safely handle # inside values"
bash -lc "$CMD"
RC=$?
echo "[DEBUG] sendevent RC=$RC"

sleep 3

AFTER_TS=$(extract_last_start)
echo "[DEBUG] AFTER_TS=$AFTER_TS"

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_from_json}",
  "environment": "{env_value}",
  "s3InboundKey": "{s3_key_in_event}",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}"
""".strip()

    print("[DEBUG] Sending SSM command. document_name:", document_name)
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
                reason = "Last Start did not increase (job may not have started or timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps: {e}"
    else:
        reason = "Missing before/after lastStart values in evidence file. Check Autosys profile + autorep format."

    return {
        "ok": True,
        "detectedEnv": env_value,
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