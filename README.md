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


# ---------------- UTILS ----------------

def sanitize(s: str) -> str:
    print("[DEBUG] sanitize() input:", s)
    out = re.sub(r"[^a-zA-Z0-9_\-\/]", "_", s or "")
    print("[DEBUG] sanitize() output:", out)
    return out


def bash_single_quote(s: str) -> str:
    print("[DEBUG] bash_single_quote() input:", s)
    if s is None:
        s = ""
    out = "'" + s.replace("'", "'\"'\"'") + "'"
    print("[DEBUG] bash_single_quote() output:", out)
    return out


def parse_mmddyyyy_hhmmss(s: str):
    print("[DEBUG] parse_mmddyyyy_hhmmss() input:", s)
    dt = datetime.strptime(s.strip(), "%m/%d/%Y %H:%M:%S")
    print("[DEBUG] parsed datetime:", dt)
    return dt


# ---------------- SSM HELPERS ----------------

def wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3):
    print("[DEBUG] wait_for_command() called")
    print("[DEBUG] command_id:", command_id)
    print("[DEBUG] instance_id:", instance_id)

    deadline = time.time() + timeout_seconds
    last_inv = None

    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id
            )
            last_inv = inv
            print("[DEBUG] SSM invocation poll:", json.dumps(inv, indent=2))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            print("[DEBUG] get_command_invocation error:", code)
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            print("[DEBUG] SSM reached terminal state:", inv.get("Status"))
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id}")


# ---------------- S3 HELPERS ----------------

def s3_get_json_with_retry(bucket, key, timeout_seconds=180, poll_seconds=3):
    print("[DEBUG] s3_get_json_with_retry()")
    print("[DEBUG] bucket:", bucket)
    print("[DEBUG] key:", key)

    deadline = time.time() + timeout_seconds
    last_err = None

    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8")
            print("[DEBUG] Raw evidence JSON:", body)
            return json.loads(body)
        except ClientError as e:
            last_err = e
            code = e.response.get("Error", {}).get("Code")
            print("[DEBUG] S3 error code:", code)
            if code in ("NoSuchKey", "NoSuchBucket"):
                time.sleep(poll_seconds)
                continue
            raise
        except Exception as e:
            last_err = e
            print("[DEBUG] Non-S3 exception reading evidence:", e)
            time.sleep(poll_seconds)

    raise TimeoutError(f"Evidence JSON not found. Last error: {last_err}")


# ---------------- MAPPING ----------------

def load_job_mapping():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autosys_job_mapping.json")
    print("[DEBUG] Loading mapping file:", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("[DEBUG] Loaded mapping keys:")
    for k in data:
        print("   ", k)
    return data


def pick_trigger_text(event):
    print("[DEBUG] pick_trigger_text() called")
    detail = event.get("detail") or {}
    print("[DEBUG] detail object:", json.dumps(detail, indent=2))

    candidates = [
        "alert_name", "alertName", "name",
        "message", "title", "eventName",
        "summary"
    ]

    for k in candidates:
        v = detail.get(k)
        if isinstance(v, str) and v.strip():
            print(f"[DEBUG] Using trigger text from detail['{k}']:", v)
            return v.strip()

    print("[DEBUG] No standard field found, using full detail JSON")
    return json.dumps(detail)


def match_mapping(trigger_text, mapping):
    print("[DEBUG] match_mapping()")
    print("[DEBUG] trigger_text:", trigger_text)

    for pattern, value in mapping.items():
        print("[DEBUG] Trying regex pattern:", pattern)
        try:
            if re.search(pattern, trigger_text):
                print("[DEBUG] MATCH FOUND for pattern:", pattern)
                print("[DEBUG] Matched mapping value:", json.dumps(value, indent=2))
                return pattern, value
        except re.error as e:
            print("[DEBUG] Invalid regex skipped:", pattern, e)

    print("[DEBUG] No regex patterns matched")
    return None, None


def extract_job_from_command(cmd):
    print("[DEBUG] extract_job_from_command() input:", cmd)
    m = re.search(r"(?:^|\s)-(?:J|j)\s+([^\s]+)", cmd or "")
    job = m.group(1) if m else ""
    print("[DEBUG] extracted job:", job)
    return job


# ---------------- LAMBDA ----------------

def lambda_handler(event, context):
    print("========== LAMBDA START ==========")
    print("[DEBUG] RAW EVENT:")
    print(json.dumps(event, indent=2))

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

    mapping = load_job_mapping()

    trigger_text = pick_trigger_text(event)
    matched_pattern, matched = match_mapping(trigger_text, mapping)

    if not matched:
        print("[ERROR] No mapping matched")
        return {
            "ok": False,
            "error": "No mapping matched",
            "triggerText": trigger_text
        }

    job_from_json = (matched.get("job_name") or "").strip()
    cmd_from_json = (matched.get("command") or "").strip()

    print("[DEBUG] job_from_json:", job_from_json)
    print("[DEBUG] cmd_from_json:", cmd_from_json)

    if not cmd_from_json and job_from_json:
        print("[DEBUG] command missing, treating job_name as full command")
        cmd_from_json = job_from_json

    if not job_from_json and cmd_from_json:
        job_from_json = extract_job_from_command(cmd_from_json)

    print("[DEBUG] FINAL JOB:", job_from_json)
    print("[DEBUG] FINAL CMD:", cmd_from_json)

    job_safe = sanitize(job_from_json)
    run_id = str(int(time.time()))
    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    print("[DEBUG] local_file:", local_file)
    print("[DEBUG] s3_key:", s3_key)

    job_literal = bash_single_quote(job_from_json)
    cmd_literal = bash_single_quote(cmd_from_json)

    print("[DEBUG] job_literal:", job_literal)
    print("[DEBUG] cmd_literal:", cmd_literal)

    remote_script = f"""bash -s <<'EOS'
set -e
JOB={job_literal}
CMD={cmd_literal}
echo "JOB=$JOB"
echo "CMD=$CMD"
{cmd_from_json}
EOS
"""

    print("[DEBUG] Remote script being sent to SSM:")
    print(remote_script)

    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user]
        },
        Comment="Autosys trigger with full debug logging"
    )

    command_id = resp["Command"]["CommandId"]
    print("[DEBUG] SSM command_id:", command_id)

    inv = wait_for_command(command_id, instance_id)
    print("[DEBUG] Final SSM invocation:")
    print(json.dumps(inv, indent=2))

    evidence = s3_get_json_with_retry(bucket, s3_key)
    print("[DEBUG] Evidence JSON parsed:")
    print(json.dumps(evidence, indent=2))

    before_ts = (evidence.get("lastStartBefore") or "").strip()
    after_ts = (evidence.get("lastStartAfter") or "").strip()

    print("[DEBUG] before_ts:", before_ts)
    print("[DEBUG] after_ts:", after_ts)

    started_confirmed = False
    reason = None

    if before_ts and after_ts:
        dt_before = parse_mmddyyyy_hhmmss(before_ts)
        dt_after = parse_mmddyyyy_hhmmss(after_ts)
        if dt_after > dt_before:
            started_confirmed = True
            reason = "Last start increased"
        else:
            reason = "Last start did not increase"
    else:
        reason = "Missing before/after timestamps"

    print("[DEBUG] started_confirmed:", started_confirmed)
    print("[DEBUG] reason:", reason)

    print("========== LAMBDA END ==========")

    return {
        "ok": True,
        "matchedPattern": matched_pattern,
        "autosysJobName": job_from_json,
        "autosysCommand": cmd_from_json,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "ssmStatus": inv.get("Status"),
        "ssmResponseCode": inv.get("ResponseCode"),
        "evidenceS3Key": s3_key
    }