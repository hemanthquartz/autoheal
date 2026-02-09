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


def bash_single_quote(s: str) -> str:
    if s is None:
        s = ""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    print("[DEBUG] wait_for_command:", command_id, instance_id)
    deadline = time.time() + timeout_seconds
    last_inv = None

    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last_inv = inv
            print("[DEBUG] SSM poll status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            print("[DEBUG] get_command_invocation error:", code)
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            print("[DEBUG] SSM terminal:", inv.get("Status"))
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last: {last_inv}")


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3):
    print("[DEBUG] s3_get_json_with_retry bucket/key:", bucket, key)
    deadline = time.time() + timeout_seconds
    last_err = None

    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8")
            print("[DEBUG] Evidence raw:", body)
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = e.response.get("Error", {}).get("Code", "")
            print("[DEBUG] Evidence not ready yet. S3 code:", code)
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            print("[DEBUG] Evidence parse/read error:", e)
            time.sleep(poll_seconds)

    raise TimeoutError(f"Evidence JSON not found in time s3://{bucket}/{key}. Last error: {last_err}")


def parse_mmddyyyy_hhmmss(s: str):
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
            # arn:aws:s3:::bucket/key...
            k = arn.split("arn:aws:s3:::")[-1]
            # remove leading bucket/
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
      SAM_HANGINGUPB_Start_20260203.complete  -> SAM_HANGINGUPB_Start
      SAM_FICC_Start_20260203.complete       -> SAM_FICC_Start
    Rules:
      - remove .complete suffix
      - remove trailing _<digits> (timestamp)
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
    m = re.search(r"(?:^|\s)-(?:J|j)\s+([^\s]+)", cmd.strip() if cmd else "")
    return m.group(1) if m else ""


def lambda_handler(event, context):
    print("========== LAMBDA START ==========")
    print("[DEBUG] RAW EVENT:", json.dumps(event, indent=2))

    # ---- CONFIG ----
    bucket = "fundacntg-devl-ftbu-us-east-1"
    prefix = "prepare/cin/dflt/SAM/test_ybyo/"
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"

    detail = event.get("detail") or {}
    document_name = event.get("documentName") or detail.get("documentName") or "fundacntg-shellssmdoc-stepfunc"

    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] run_as_user:", run_as_user)
    print("[DEBUG] document_name:", document_name)

    mapping = load_job_mapping("autosys_job_mapping.json")

    s3_key_in_event = extract_s3_key_from_event(event)
    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract S3 object key from event", "eventKeys": list(event.keys())}

    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        # helpful debug: show "closest" keys by substring
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
            "suggestions": suggestions,
        }

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job_from_json:", job_from_json)
    print("[DEBUG] cmd_from_json:", cmd_from_json)

    if not cmd_from_json and job_from_json:
        print("[DEBUG] command missing; treating job_name as full command")
        cmd_from_json = job_from_json

    if not job_from_json and cmd_from_json:
        print("[DEBUG] job_name missing; extracting job from command")
        job_from_json = extract_job_from_command(cmd_from_json)

    if not job_from_json or not cmd_from_json:
        return {
            "ok": False,
            "error": "Mapping found but missing job_name/command after normalization",
            "derivedKey": map_key,
            "matched": matched,
            "job_from_json": job_from_json,
            "cmd_from_json": cmd_from_json,
        }

    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] evidence_s3_key:", evidence_s3_key)

    job_literal = bash_single_quote(job_from_json)
    cmd_literal = bash_single_quote(cmd_from_json)

    print("[DEBUG] job_literal:", job_literal)
    print("[DEBUG] cmd_literal:", cmd_literal)

    remote_script = f"""bash -s <<'EOS'
set -e

JOB={job_literal}
CMD={cmd_literal}

echo "=== JOB ==="
echo "$JOB"
echo "=== CMD ==="
echo "$CMD"
echo "==========="

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
aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}"
echo "Uploaded evidence to s3://{bucket}/{evidence_s3_key}"
EOS
""".strip()

    print("[DEBUG] remote_script (first 500 chars):")
    print(remote_script[:500])

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger (filename mapping) + evidence saved locally and uploaded to S3",
    )

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("[DEBUG] Final SSM invocation status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))

    evidence = s3_get_json_with_retry(bucket, evidence_s3_key, timeout_seconds=180, poll_seconds=3)
    print("[DEBUG] Evidence JSON:", json.dumps(evidence, indent=2))

    before_ts = (evidence.get("lastStartBefore") or "").strip()
    after_ts = (evidence.get("lastStartAfter") or "").strip()

    started_confirmed = False
    reason = None

    if before_ts and after_ts:
        dt_before = parse_mmddyyyy_hhmmss(before_ts)
        dt_after = parse_mmddyyyy_hhmmss(after_ts)
        if dt_after > dt_before:
            started_confirmed = True
            reason = "Last Start increased after command (strong confirmation job started)"
        else:
            started_confirmed = False
            reason = "Last Start did not increase (job may not have started or timestamp didn't change yet)"
    else:
        reason = "Missing before/after lastStart values in evidence. Check commandOutput."

    print("[DEBUG] started_confirmed:", started_confirmed)
    print("[DEBUG] reason:", reason)
    print("========== LAMBDA END ==========")

    return {
        "ok": True,
        "s3ObjectKey": s3_key_in_event,
        "filename": filename,
        "derivedKey": map_key,
        "autosysJobName": job_from_json,
        "autosysCommand": cmd_from_json,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendEventRC": evidence.get("sendEventRC"),
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
        "commandOutput": evidence.get("commandOutput"),
    }