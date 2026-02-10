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
    Safe-ish string for S3 folder names.
    (No regex)
    """
    if not s:
        return ""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return "".join(ch if ch in allowed else "_" for ch in s)


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
            code = (e.response.get("Error") or {}).get("Code", "")
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(poll_seconds)

    raise TimeoutError(f"Evidence JSON not found in time s3://{bucket}/{key}. Last err: {last_err}")


def parse_mmddyyyy_hhmmss(s: str):
    # Example: 01/30/2026 02:41:11
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def load_job_mapping(filename: str = "autosys_job_mapping.json") -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    print("[DEBUG] Loading mapping file:", path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("[DEBUG] Mapping keys count:", len(list(data.keys())))
    print("[DEBUG] First 20 mapping keys:", list(data.keys())[:20])
    return data


def extract_s3_key_from_event(event: dict) -> str:
    """
    Supports EventBridge/CloudTrail style events.
    Prefer: detail.requestParameters.key
    Fallback: resources[].arn for s3 object.
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
            after_prefix = arn.split("arn:aws:s3:::", 1)[1]
            parts = after_prefix.split("/", 1)
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find s3 key in event")
    return ""


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example filename:
      SAM_HANGINGUPB_Start_20260203.complete  -> SAM_HANGINGUPB_Start

    Rules (NO regex):
      - remove ".complete" suffix
      - remove trailing "_<digits>" (timestamp)
    """
    print("[DEBUG] normalize input filename:", filename)

    name = filename or ""
    if name.endswith(".complete"):
        name = name[: -len(".complete")]

    # remove trailing digits
    i = len(name) - 1
    while i >= 0 and name[i].isdigit():
        i -= 1

    # if we stopped at an underscore before digits, remove that underscore too
    if i >= 0 and name[i] == "_" and i < len(name) - 1:
        name = name[:i]
    else:
        name = name[: i + 1]

    print("[DEBUG] normalized mapping key:", name)
    return name


def extract_env_from_s3_key(s3_key: str) -> str:
    """
    Extract env segment like DEVL1 from the S3 path.
    Your example:
      inbox/.../OUT/DEVL1/SCD/....complete  -> DEVL1
    NO regex: scan segments.
    """
    if not s3_key:
        return ""

    parts = [p for p in s3_key.split("/") if p]
    print("[DEBUG] S3 key parts:", parts)

    for seg in parts:
        up = seg.upper()
        if up.startswith("DEVL") and len(up) > 4:
            ok = True
            for ch in up[4:]:
                if not ch.isdigit():
                    ok = False
                    break
            if ok:
                print("[DEBUG] Environment extracted from S3 key path:", up)
                return up

    print("[DEBUG] No environment segment found in S3 key path")
    return ""


def apply_logenv_replacement(job_name: str, command: str, env_from_path: str):
    """
    Replace LOGENV placeholder inside JSON values with the env extracted from S3.
    Example:
      GV7#..._LOGENV  -> GV7#..._DEVL1
    """
    if not env_from_path:
        print("[DEBUG] env_from_path empty -> cannot replace LOGENV")
        return job_name, command, False

    changed = False
    if "LOGENV" in (job_name or ""):
        job_name = job_name.replace("LOGENV", env_from_path)
        changed = True

    if "LOGENV" in (command or ""):
        command = command.replace("LOGENV", env_from_path)
        changed = True

    print("[DEBUG] LOGENV replacement changed:", changed)
    print("[DEBUG] job_name AFTER:", job_name)
    print("[DEBUG] command AFTER :", command)

    return job_name, command, changed


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ---- CONFIG ----
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/ADHOC_BUS_REQ/test_ybyo/"
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"

    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"
    print("[DEBUG] document_name:", document_name)

    mapping = load_job_mapping("autosys_job_mapping.json")

    s3_key_in_event = extract_s3_key_from_event(event)
    print("[DEBUG] s3_key_in_event:", s3_key_in_event)

    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract s3 object key from event", "eventKeys": list(event.keys())}

    env_from_path = extract_env_from_s3_key(s3_key_in_event)
    print("[DEBUG] env_from_path:", env_from_path)

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
            "suggestions": suggestions,
        }

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job_from_json BEFORE:", job_from_json)
    print("[DEBUG] cmd_from_json BEFORE:", cmd_from_json)

    # ✅ Replace LOGENV using env from S3 path
    job_from_json, cmd_from_json, logenv_replaced = apply_logenv_replacement(job_from_json, cmd_from_json, env_from_path)

    if not logenv_replaced:
        print("[WARN] LOGENV was not replaced. Either env was missing or JSON values do not contain LOGENV.")

    # Evidence file naming
    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] job_safe:", job_safe)
    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] evidence_s3_key:", evidence_s3_key)

    # Use env_from_path also in profile path (so we don't hardcode DEVL1 here)
    # NOTE: If your profile path is not env-specific, you can keep it fixed.
    profile_path = f"/export/app1/gv7/gv7dev1/src/{env_from_path}/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
    print("[DEBUG] profile_path:", profile_path)

    remote_script = f"""
set -e
JOB="{job_from_json}"

# Load Autosys profile if present (env-aware)
if [ -f "{profile_path}" ]; then
  source "{profile_path}"
fi

extract_last_start() {{
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  if [ -z "$LINE" ]; then
    echo ""
    return 0
  fi

  DATE_PART=$(echo "$LINE" | awk '{{for(i=1;i<=NF;i++) if ($i ~ /\\/\\//) {{print $i; exit}}}}')
  TIME_PART=$(echo "$LINE" | awk '{{for(i=1;i<=NF;i++) if ($i ~ /:/) {{print $i; exit}}}}')

  if [ -n "$DATE_PART" ] && [ -n "$TIME_PART" ]; then
    echo "$DATE_PART $TIME_PART"
  else
    echo ""
  fi
}}

BEFORE_TS=$(extract_last_start)

# ---- Run the mapped command (may contain #, keep as-is) ----
{cmd_from_json}
RC=$?

sleep 3
AFTER_TS=$(extract_last_start)

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "{local_file}" << EOF
{{
  "jobName": "{job_from_json}",
  "environmentFromS3Path": "{env_from_path}",
  "logenvReplaced": {str(logenv_replaced).lower()},
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}"
}}
EOF

aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}"
""".strip()

    print("[DEBUG] remote_script (first 2000 chars):")
    print(remote_script[:2000])

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
                reason = "Last Start did not increase (job may not have started yet or timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps. Error: {str(e)}"
    else:
        reason = "Missing before/after lastStart values in local evidence file. Check Autosys profile + autorep output format."

    return {
        "ok": True,
        "s3ObjectKey": s3_key_in_event,
        "environmentFromS3Path": env_from_path or None,
        "logenvReplaced": logenv_replaced,
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