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
    # Keep safe chars for S3 keys and filenames
    return re.sub(r"[^a-zA-Z0-9_\-\/]", "_", s or "")


def bash_single_quote(s: str) -> str:
    # Wrap a string for bash safely using single quotes
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


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 600, poll_seconds: int = 3):
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
    # example: 02/09/2026 19:03:11
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")


def load_job_mapping(filename: str = "autosys_job_mapping.json") -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    print("[DEBUG] Loading mapping:", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("[DEBUG] Mapping keys:", list(data.keys())[:50])
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
            # arn:aws:s3:::bucket/key
            k = arn.split("arn:aws:s3:::", 1)[-1]
            parts = k.split("/", 1)  # [bucket, key]
            if len(parts) == 2:
                key2 = parts[1]
                print("[DEBUG] S3 key from resources ARN:", key2)
                return key2

    print("[DEBUG] Could not find S3 key in event")
    return ""


def normalize_filename_to_mapping_key(filename: str) -> str:
    """
    Example filename:
      SAM_HANGINGUPB_Start_20260203.complete -> SAM_HANGINGUPB_Start
      SAM_FICC_Start_20260203.complete      -> SAM_FICC_Start

    Rules:
      - remove .complete suffix
      - remove trailing _<digits> (timestamp/date)
    """
    print("[DEBUG] normalize input filename:", filename)
    name = filename or ""

    if name.endswith(".complete"):
        name = name[: -len(".complete")]

    # remove trailing _digits (like _20260203 or _1700000000)
    name = re.sub(r"_[0-9]+$", "", name)

    print("[DEBUG] normalized mapping key:", name)
    return name


def extract_job_from_command(cmd: str) -> str:
    # try to parse "-j JOBNAME" from sendevent command
    m = re.search(r"(?:^|\s)-j\s+([^\s]+)", (cmd or "").strip())
    return m.group(1) if m else ""


def build_remote_script(bucket: str, evidence_s3_key: str, instance_id: str, run_as_user: str,
                        job_from_json: str, cmd_from_json: str, local_file: str) -> str:
    """
    Remote script:
      - capture BEFORE_TS from autorep
      - run sendevent command
      - capture AFTER_TS from autorep
      - write evidence JSON locally
      - upload to S3
      - VERIFY with head-object retries (this fixes your NoSuchKey)
    """

    job_literal = bash_single_quote(job_from_json)
    cmd_literal = bash_single_quote(cmd_from_json)
    bucket_literal = bash_single_quote(bucket)
    key_literal = bash_single_quote(evidence_s3_key)
    local_file_literal = bash_single_quote(local_file)
    instance_literal = bash_single_quote(instance_id)

    script = f"""bash -s <<'EOS'
set -euo pipefail

BUCKET={bucket_literal}
EVIDENCE_KEY={key_literal}
LOCAL_FILE={local_file_literal}
INSTANCE_ID={instance_literal}

JOB={job_literal}
CMD={cmd_literal}

echo "[DEBUG] Running as user: $(whoami)"
echo "[DEBUG] JOB=$JOB"
echo "[DEBUG] CMD=$CMD"
echo "[DEBUG] LOCAL_FILE=$LOCAL_FILE"
echo "[DEBUG] S3_TARGET=s3://$BUCKET/$EVIDENCE_KEY"

# Load Autosys profile if available
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  # shellcheck disable=SC1091
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

extract_last_start() {{
  LINE=$(autorep -j "$JOB" | grep "$JOB" | head -n 1 || true)
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' || true
}}

BEFORE_TS=$(extract_last_start)
echo "[DEBUG] BEFORE_TS=$BEFORE_TS"

# Run the command
# NOTE: this is your mapped full command (ex: sendevent -E ... -j ...)
eval "$CMD"
RC=$?
echo "[DEBUG] send event RC=$RC"

sleep 3

AFTER_TS=$(extract_last_start)
echo "[DEBUG] AFTER_TS=$AFTER_TS"

NOW_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$LOCAL_FILE" << EOF
{{
  "jobName": "$JOB",
  "command": "$CMD",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "sendeventRc": "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "$INSTANCE_ID",
  "s3Bucket": "$BUCKET",
  "s3Key": "$EVIDENCE_KEY"
}}
EOF

echo "[DEBUG] Evidence file created:"
ls -l "$LOCAL_FILE" || true
echo "[DEBUG] Evidence content:"
cat "$LOCAL_FILE" || true

# Upload and VERIFY
aws s3 cp "$LOCAL_FILE" "s3://$BUCKET/$EVIDENCE_KEY"
echo "[DEBUG] Upload done. Verifying head-object..."

VERIFY_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  if aws s3api head-object --bucket "$BUCKET" --key "$EVIDENCE_KEY" >/dev/null 2>&1; then
    VERIFY_OK=1
    echo "[DEBUG] head-object OK (attempt $i)"
    break
  fi
  echo "[DEBUG] head-object not found yet (attempt $i) - sleeping 2s"
  sleep 2
done

if [ "$VERIFY_OK" -ne 1 ]; then
  echo "[ERROR] Upload verification failed: s3://$BUCKET/$EVIDENCE_KEY not found after retries"
  exit 2
fi

echo "[DEBUG] Remote script completed successfully"
EOS
""".strip()

    return script


def lambda_handler(event, context):
    print("=========== LAMBDA START ===========")
    print("[DEBUG] RAW EVENT:", json.dumps(event, indent=2))

    # -------- CONFIG (keep yours here) --------
    bucket = "fundacntg-dev1-ftbu-us-east-1"
    prefix = "prepare/cin/dfl/SAM/test_ybyo/"   # IMPORTANT: no leading slash
    instance_id = "i-090e6f0a08fa26397"
    run_as_user = "gauhlk"
    document_name = "fundacntg-shellssmdoc-stepfunc"  # your SSM document
    mapping_file = "autosys_job_mapping.json"
    # -----------------------------------------

    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] run_as_user:", run_as_user)
    print("[DEBUG] document_name:", document_name)

    mapping = load_job_mapping(mapping_file)

    s3_key_in_event = extract_s3_key_from_event(event)
    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract S3 object key from event", "eventKeys": list(event.keys())}

    filename = s3_key_in_event.split("/")[-1]
    print("[DEBUG] filename:", filename)

    map_key = normalize_filename_to_mapping_key(filename)
    print("[DEBUG] map_key:", map_key)

    matched = mapping.get(map_key)
    if not matched:
        suggestions = [k for k in mapping.keys() if (k in map_key or map_key in k)]
        print("[ERROR] No mapping for key:", map_key)
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

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job_from_json:", job_from_json)
    print("[DEBUG] cmd_from_json:", cmd_from_json)

    # If mapping stores full command in "job_name" (older style), accept it
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

    print("[DEBUG] job_safe:", job_safe)
    print("[DEBUG] run_id:", run_id)
    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] evidence_s3_key:", evidence_s3_key)

    remote_script = build_remote_script(
        bucket=bucket,
        evidence_s3_key=evidence_s3_key,
        instance_id=instance_id,
        run_as_user=run_as_user,
        job_from_json=job_from_json,
        cmd_from_json=cmd_from_json,
        local_file=local_file,
    )

    print("[DEBUG] Remote script:\n", remote_script)

    # Run SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger + evidence saved locally + uploaded to S3 (verified via head-object)",
    )

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id)
    print("SSM Status:", inv.get("Status"), inv.get("ResponseCode"))

    # If SSM failed, return its output to debug immediately
    if inv.get("Status") != "Success":
        return {
            "ok": False,
            "error": "SSM command did not succeed",
            "ssm": {
                "commandId": command_id,
                "instanceId": instance_id,
                "documentName": document_name,
                "runAsUser": run_as_user,
                "status": inv.get("Status"),
                "responseCode": inv.get("ResponseCode"),
                "stdout": inv.get("StandardOutputContent"),
                "stderr": inv.get("StandardErrorContent"),
            },
            "expectedEvidence": {"bucket": bucket, "key": evidence_s3_key},
        }

    # Fetch evidence from S3 (now remote script verifies it exists)
    try:
        evidence = s3_get_json_with_retry(bucket, evidence_s3_key, timeout_seconds=600, poll_seconds=3)
    except Exception as e:
        # Provide SSM stdout/stderr so you can see if aws s3 cp/head-object failed
        return {
            "ok": False,
            "error": "Evidence JSON not readable from S3 in time",
            "exception": str(e),
            "expectedEvidence": {"bucket": bucket, "key": evidence_s3_key},
            "ssm": {
                "commandId": command_id,
                "instanceId": instance_id,
                "status": inv.get("Status"),
                "responseCode": inv.get("ResponseCode"),
                "stdout": inv.get("StandardOutputContent"),
                "stderr": inv.get("StandardErrorContent"),
            },
        }

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
                reason = "Last Start did not increase"
        except Exception as e:
            reason = f"Could not parse before/after timestamps: {e}"
    else:
        reason = "Missing before/after lastStart values in evidence file"

    return {
        "ok": True,
        "autosysJobName": evidence.get("jobName") or job_from_json,
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