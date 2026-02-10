import json
import time
import re
from datetime import datetime
import os
import boto3
from boto3.exceptions import ClientError

ssm = boto3.client('ssm')
s3 = boto3.client('s3')

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}

def sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "", s) or ""

def bash_single_quote(s: str) -> str:
    if s is None:
        s = ""
    return "'" + s.replace("'", "'\\''") + "'"

def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_inv = None
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last_inv = inv
            print("[DEBUG] SSM poll status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            print("[DEBUG] Get command invocation error:", code)
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
        if inv.get("Status") in TERMINAL_STATUSES:
            print("[DEBUG] SSM terminal:", inv.get("Status"))
            return inv
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last: {last_inv}")

def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_err = None
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj['Body'].read().decode('utf-8')
            print("[DEBUG] Body:", body)
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = e.response.get("Error", {}).get("Code", "Unknown")
            print("[DEBUG] Evidence not ready yet. S3 code:", code)
            if code == "NoSuchKey":
                time.sleep(poll_seconds)
                continue
            raise e
        time.sleep(poll_seconds)
    raise TimeoutError(f"Evidence JSON not found in time s3://{bucket}/{key}. Last error: {last_err}")

def parse_mdyyyy_hhmmss(s: str):
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")

def load_job_mapping(filename: str = 'autosys_job_mapping.json') -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)
    print("[DEBUG] Loading mapping:", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("[DEBUG] Mapping keys:", list(data.keys()))
    return data

def extract_s3_key_from_event(event: dict) -> str:
    detail = event.get("detail") or {}
    req = detail.get("requestParameters") or {}
    key = req.get("key")
    if isinstance(key, str) and key.strip():
        print("[DEBUG] s3 key from key:", key)
        return key
    resources = event.get("resources") or []
    for r in resources:
        arn = r.get("ARN")
        if isinstance(arn, str) and arn.startswith("arn:aws:s3:::") and "/" in arn:
            k = arn.split("arn:aws:s3:::", 1)[1].split("/", 1)[1]
            return k
    return ""

def normalize_filename_to_mapping_key(filename: str) -> str:
    name = filename
    if name.endswith(".complete"):
        name = name[:-len(".complete")]
    name = re.sub(r"_\d+$", "", name)
    print("[DEBUG] normalized mapping key:", name)
    return name

def extract_job_from_command(cmd: str) -> str:
    m = re.search(r'\-J\s+([^\s]+)', cmd.strip())
    if m:
        return m.group(1)
    return ""

def lambda_handler(event, context):
    print("[DEBUG] RAW EVENT:", json.dumps(event, indent=2))
    bucket = "fundacntg-devl1-ftbu-us-east-1"
    prefix = "prepare/cin/dfit/SAM/test-ybvo/"
    run_as_user = "gauhlk"
    document_name = "fundacntg-shellssmdoc-stepfunc"
    instance_id = "i-090e6f0a8fa26397"
    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] prefix:", prefix)
    print("[DEBUG] instance_id:", instance_id)
    print("[DEBUG] document_name:", document_name)
    print("[DEBUG] run_as_user:", run_as_user)
    mapping = load_job_mapping()
    s3_key_in_event = extract_s3_key_from_event(event)
    if not s3_key_in_event:
        return {"ok": False, "error": "Could not extract s3 object key from event", "eventKeys": list(event.keys())}
    filename = s3_key_in_event.split("/")[-1]
    map_key = normalize_filename_to_mapping_key(filename)
    matched = mapping.get(map_key)
    if not matched:
        suggestions = [k for k in mapping.keys() if map_key in k or k in map_key]
        return {"ok": False, "error": "No mapping matched filename-derived key", "s3ObjectKey": s3_key_in_event, "filename": filename, "derivedKey": map_key, "availableKeys": list(mapping.keys())[:50], "suggestions": suggestions}
    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()
    print("[DEBUG] matched JSON entry:", json.dumps(matched, indent=2))
    print("[DEBUG] job from json:", job_from_json)
    print("[DEBUG] cmd from json:", cmd_from_json)
    if not job_from_json or not cmd_from_json:
        return {"ok": False, "error": "Mapping found but missing job_name/command after normalization", "derivedKey": map_key, "matched": matched, "job_from_json": job_from_json, "cmd_from_json": cmd_from_json}
    run_id = os.urandom(4).hex()
    job_safe = sanitize(job_from_json)
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    evidence_s3_key = f"{prefix.rstrip('/')}/{job_safe}/run_{run_id}.json"
    print("[DEBUG] local file:", local_file)
    print("[DEBUG] evidence s3 key:", evidence_s3_key)
    job_literal = bash_single_quote(job_from_json)
    cmd_literal = bash_single_quote(cmd_from_json)
    print("[DEBUG] job literal:", job_literal)
    print("[DEBUG] cmd literal:", cmd_literal)
    remote_script = f"""bash -s << 'EOS'
JOB={job_literal}
CMD={cmd_literal}
echo "[DEBUG] Running as user: $(whoami)"
echo "[DEBUG] JOB=$JOB"
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7.pysrc/config/infa.autosys.profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7.pysrc/config/infa.autosys.profile.ksh
  echo "[DEBUG] Profile sourced successfully"
else
  echo "[DEBUG] Profile not found - autosys commands may fail"
fi
extract_last_start() {{
  AUTOREP_OUTPUT=$(autorep -J "$JOB" 2>&1)
  echo "[DEBUG] Autorep raw output: $AUTOREP_OUTPUT"
  LINE=$(echo "$AUTOREP_OUTPUT" | grep "$JOB" | head -n 1 | true)
  echo "[DEBUG] Filtered line: $LINE"
  echo "$LINE" | grep -Eo '[0-9]{{1,2}}/[0-9]{{1,2}}/[0-9]{{4}} [0-9]{{1,2}}:[0-9]{{2}}:[0-9]{{2}}' | true
}}
BEFORE_TS=$(extract_last_start)
CMD_OUTPUT=$($CMD 2>&1)
RC=$?
echo "[DEBUG] Sendevent output: $CMD_OUTPUT"
sleep 3
AFTER_TS=$(extract_last_start)
NOW_ISO=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
cat > "{local_file}" << EOF
{{
  "JobName": {job_literal},
  "LastStartBefore": "$BEFORE_TS",
  "LastStartAfter": "$AFTER_TS",
  "sendeventRc": $RC,
  "capturedAtUtc": "$NOW_ISO",
  "instanceId": "{instance_id}",
  "sendeventOutput": "$CMD_OUTPUT"
}}
EOF
UPLOAD_OUTPUT=$(aws s3 cp "{local_file}" "s3://{bucket}/{evidence_s3_key}" 2>&1)
UPLOAD_RC=$?
echo "[DEBUG] Upload output: $UPLOAD_OUTPUT"
echo "[DEBUG] Upload RC: $UPLOAD_RC"
EOS
"""
    print("[DEBUG] Remote script:\n", remote_script)
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user]
        },
        Comment="Autosys trigger + evidence saved locally and uploaded to s3"
    )
    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM CommandId:", command_id)
    inv = wait_for_command(command_id, instance_id)
    print("[SSM Status:", inv.get("Status"), inv.get("ResponseCode"))
    evidence = s3_get_json_with_retry(bucket, evidence_s3_key)
    before_ts = (evidence.get("LastStartBefore") or "").strip()
    after_ts = (evidence.get("LastStartAfter") or "").strip()
    started_confirmed = False
    reason = None
    if before_ts and after_ts:
        dt_before = parse_mdyyyy_hhmmss(before_ts)
        dt_after = parse_mdyyyy_hhmmss(after_ts)
        if dt_after > dt_before:
            started_confirmed = True
            reason = "Last Start increased after sendevent (strong confirmation job started)"
        else:
            reason = "Last Start did not increase"
    elif not before_ts and after_ts:
        started_confirmed = True
        reason = "No prior start time, but set after sendevent (confirmation job started)"
    else:
        reason = "Missing before/after LastStart values in evidence file"
    return {
        "ok": started_confirmed,
        "autosysJobName": job_from_json,
        "autosysStartConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "sendeventRc": evidence.get("sendeventRc"),
        "evidenceLocation": {
            "localFileOnInstance": local_file,
            "s3Bucket": bucket,
            "s3Key": evidence_s3_key
        },
        "ssm": {
            "CommandId": command_id,
            "InstanceId": instance_id,
            "documentName": document_name,
            "runAsUser": run_as_user,
            "Status": inv.get("Status"),
            "ResponseCode": inv.get("ResponseCode")
        }
    }
```fundac