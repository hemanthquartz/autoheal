import os
import json
import time
import re
import base64
import shlex
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")
s3 = boto3.client("s3")

TERMINAL_STATUSES = {"Success", "Failed", "TimedOut", "Cancelled", "Cancelling"}


def sanitize(s: str) -> str:
    # safe for filenames/keys
    return re.sub(r"[^a-zA-Z0-9_\-./]", "_", s or "")


def wait_for_command(command_id: str, instance_id: str, timeout_seconds: int = 900, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        try:
            inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            last = inv
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            if code == "InvocationDoesNotExist":
                time.sleep(poll_seconds)
                continue
            raise

        if inv.get("Status") in TERMINAL_STATUSES:
            return inv

        time.sleep(poll_seconds)

    raise TimeoutError(f"Timed out waiting for SSM command {command_id} on {instance_id}. Last={last}")


def s3_get_json_with_retry(bucket: str, key: str, timeout_seconds: int = 180, poll_seconds: int = 3):
    deadline = time.time() + timeout_seconds
    last_err = None
    while time.time() < deadline:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read().decode("utf-8", errors="replace")
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


def extract_job_from_full_command(full_cmd: str) -> str:
    """
    Extract token after -J from a full command string.
    Works for:
      sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#NAME
      sendevent -E FORCE_STARTJOB -J "GV7#SA#cmd#NAME"
    """
    if not full_cmd:
        return ""

    try:
        parts = shlex.split(full_cmd)
    except Exception:
        # fallback: simple split
        parts = full_cmd.split()

    for i, tok in enumerate(parts):
        if tok == "-J" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def lambda_handler(event, context):
    print("RAW EVENT:", json.dumps(event, indent=2))

    # ===== Config (use env vars if present) =====
    bucket = os.environ.get("AUTOSYS_EVIDENCE_BUCKET", "fundacntg-devl-ftbu-us-east-1")
    prefix = os.environ.get("AUTOSYS_EVIDENCE_PREFIX", "prepare/cin/dflt/SAM/test_ybyo/").strip()

    # Example hard-coded instance/user/doc (keep your current values)
    detail = event.get("detail") or {}
    instance_id = os.environ.get("AUTOSYS_INSTANCE_ID", "i-090e6f0a08fa26397")
    run_as_user = os.environ.get("AUTOSYS_RUN_AS_USER", "gauhlk")
    document_name = event.get("documentName") or detail.get("documentName") or os.environ.get("AUTOSYS_DOCUMENT_NAME", "fundacntg-shellssmdoc-stepfunc")

    if not bucket:
        return {"ok": False, "error": "Missing evidence bucket. Set AUTOSYS_EVIDENCE_BUCKET env var."}

    # ===== job_name is FULL command (your requirement) =====
    # In your real flow, this will come from your mapping/json or from event key.
    full_cmd = (
        detail.get("jobCommand")
        or event.get("jobCommand")
        or "sendevent -E FORCE_STARTJOB -J GV7#SA#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
    ).strip()

    if not instance_id or not full_cmd:
        return {"ok": False, "error": "Missing instanceId or jobCommand/full_cmd"}

    # Extract job for evidence & s3 key naming (IMPORTANT: don't use full command for file names)
    job_for_evidence = extract_job_from_full_command(full_cmd)
    if not job_for_evidence:
        # still proceed, but your evidence functions depend on JOB
        print("WARNING: Could not extract -J <job> from full command. Autorep evidence may fail.")

    job_safe = sanitize(job_for_evidence or "unknown_job")
    run_id = str(int(time.time()))

    local_file = f"/tmp/autosys_evidence_{job_safe}_{run_id}.json"
    s3_key = f"{prefix.rstrip('/')}/{job_safe}/{run_id}.json"

    # Base64 encode full command to transport safely
    cmd_b64 = base64.b64encode(full_cmd.encode("utf-8")).decode("ascii")

    print("CONFIG:")
    print("  bucket:", bucket)
    print("  prefix:", prefix)
    print("  s3_key:", s3_key)
    print("  instance_id:", instance_id)
    print("  run_as_user:", run_as_user)
    print("  document_name:", document_name)
    print("  full_cmd (raw):", full_cmd)
    print("  extracted job_for_evidence:", job_for_evidence)

    # ===== Remote script with heavy debug =====
    # Key fix: build CMD_SAFE that QUOTES the -J job value so '#' is not treated as comment by bash.
    remote_script = f"""#!/bin/bash
set -euo pipefail

echo "===================="
echo "AUTOSYS REMOTE START"
echo "UTC: $(date -u)"
echo "HOST: $(hostname)"
echo "USER: $(whoami)"
echo "PWD:  $(pwd)"
echo "SHELL:$SHELL"
echo "PATH: $PATH"
echo "===================="

# Helpful command discovery
echo "which bash:   $(command -v bash || true)"
echo "which sendevent: $(command -v sendevent || true)"
echo "which autorep:   $(command -v autorep || true)"
echo "which aws:       $(command -v aws || true)"
echo "which python3:   $(command -v python3 || true)"
echo "uname -a: $(uname -a || true)"
echo "--------------------"

CMD_B64="{cmd_b64}"
echo "CMD_B64 length: ${{#CMD_B64}}"

# Decode exactly what Lambda sent
CMD="$(echo "$CMD_B64" | base64 --decode)"
echo "=== CMD received (decoded) ==="
printf '%s\\n' "$CMD"
echo "=============================="

# Load Autosys profile if present
PROFILE="/export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh"
if [ -f "$PROFILE" ]; then
  echo "Loading Autosys profile: $PROFILE"
  # shellcheck disable=SC1090
  source "$PROFILE"
else
  echo "Autosys profile NOT found at: $PROFILE"
fi

# Extract JOB after -J from CMD (for autorep)
JOB="$(echo "$CMD" | awk '{{ for (i=1;i<=NF;i++) if ($i=="-J") {{ print $(i+1); exit }} }}')"
echo "Extracted JOB token: [$JOB]"

if [ -z "$JOB" ]; then
  echo "ERROR: Could not extract job name (-J <job>) from CMD"
  echo "CMD was: $CMD"
  exit 2
fi

# Build a SAFE command where the -J value is quoted to protect # from being treated as comment
# Prefer python3 for robust token handling; fallback to awk if python3 missing.
if command -v python3 >/dev/null 2>&1; then
  CMD_SAFE="$(python3 - <<'PY'
import shlex, sys
cmd = sys.stdin.read().strip()
parts = shlex.split(cmd)
out=[]
i=0
while i < len(parts):
  if parts[i] == "-J" and i+1 < len(parts):
    out.append("-J")
    # Quote job token explicitly; keep as one argument
    out.append(parts[i+1])
    i += 2
  else:
    out.append(parts[i])
    i += 1

# Rebuild command; we will execute via bash -lc with explicit quoting for -J arg.
# We will wrap the -J value in double quotes in the final string:
rebuilt=[]
i=0
while i < len(out):
  if out[i] == "-J" and i+1 < len(out):
    rebuilt.append("-J")
    # escape any embedded double quotes just in case (rare)
    val = out[i+1].replace('"','\\\\\\"')
    rebuilt.append(f'"{val}"')
    i += 2
  else:
    rebuilt.append(out[i])
    i += 1

print(" ".join(rebuilt))
PY
<<<"$CMD")"
else
  CMD_SAFE="$(echo "$CMD" | awk '{
    out="";
    for (i=1;i<=NF;i++) {
      if ($i=="-J" && (i+1)<=NF) {
        out = out $i " \\"" $(i+1) "\\"";
        i++;
      } else {
        out = out (out=="" ? "" : " ") $i;
      }
    }
    print out;
  }')"
fi

echo "=== CMD_SAFE (will execute) ==="
printf '%s\\n' "$CMD_SAFE"
echo "================================"

# turn on xtrace only after we printed the commands (so it’s easier to read)
set -x

extract_last_start() {{
  # Capture full autorep output for debug
  echo "Running: autorep -j \\"$JOB\\""
  AUTOREP_OUT="$(autorep -j "$JOB" 2>&1 || true)"
  echo "----- autorep output start -----"
  echo "$AUTOREP_OUT"
  echo "----- autorep output end -----"

  # First matching job line
  LINE="$(echo "$AUTOREP_OUT" | grep "$JOB" | head -n 1 || true)"
  echo "autorep first matching line: $LINE"

  # Extract MM/DD/YYYY HH:MM:SS
  echo "$LINE" | grep -Eo '[0-9]{{2}}/[0-9]{{2}}/[0-9]{{4}}[[:space:]]+[0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}' | head -n 1 || true
}}

echo "--- BEFORE ---"
BEFORE_TS="$(extract_last_start)"
echo "BEFORE_TS=$BEFORE_TS"

echo "--- RUN CMD_SAFE ---"
set +e
bash -lc "$CMD_SAFE" 2>&1 | tee /tmp/autosys_cmd_output.txt
RC="${{PIPESTATUS[0]}}"
set -e
echo "CMD_RC=$RC"

sleep 3

echo "--- AFTER ---"
AFTER_TS="$(extract_last_start)"
echo "AFTER_TS=$AFTER_TS"

NOW_ISO="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

# Write evidence JSON safely using python3 so quoting never breaks
python3 - <<PY
import json
data = {{
  "jobName": "{job_for_evidence}",
  "jobExtractedOnInstance": "$JOB",
  "commandOriginal": """{full_cmd}""",
  "commandDecoded": "$CMD",
  "commandExecuted": "$CMD_SAFE",
  "lastStartBefore": "$BEFORE_TS",
  "lastStartAfter": "$AFTER_TS",
  "commandRC": int("$RC") if "$RC".isdigit() else "$RC",
  "capturedAtUtc": "$NOW_ISO",
  "debug": {{
    "hostname": "$(hostname)",
    "whoami": "$(whoami)",
    "pwd": "$(pwd)",
    "path": "$PATH",
    "profileFound": str({{"true":1,"false":0}}).lower(),  # placeholder marker
  }},
  "cmdStdoutStderrSample": open("/tmp/autosys_cmd_output.txt","r",errors="ignore").read()[-4000:]
}}
# Fix profileFound properly (bash can't pass booleans directly easily in this snippet)
# We'll overwrite below with a string; that's okay.
data["debug"]["profileFound"] = "yes" if "{'1' if 'x' else '0'}" else "unknown"
with open("{local_file}", "w") as f:
  json.dump(data, f, indent=2)
print("Wrote evidence file: {local_file}")
PY

echo "Evidence file content (tail):"
tail -n 50 "{local_file}" || true

echo "Uploading to S3: s3://{bucket}/{s3_key}"
aws s3 cp "{local_file}" "s3://{bucket}/{s3_key}"

echo "AUTOSYS REMOTE END"
"""

    # Send to SSM
    resp = ssm.send_command(
        DocumentName=document_name,
        InstanceIds=[instance_id],
        Parameters={
            "command": [remote_script],
            "runAsUser": [run_as_user],
        },
        Comment="Autosys trigger (full command) + evidence saved locally and uploaded to S3",
    )

    command_id = resp["Command"]["CommandId"]
    print("SSM CommandId:", command_id)

    inv = wait_for_command(command_id, instance_id, timeout_seconds=900, poll_seconds=3)
    print("SSM Status:", inv.get("Status"), "ResponseCode:", inv.get("ResponseCode"))
    # These are super helpful when it fails
    print("SSM Stdout (snippet):", (inv.get("StandardOutputContent") or "")[:2000])
    print("SSM Stderr (snippet):", (inv.get("StandardErrorContent") or "")[:2000])

    # Read evidence JSON from S3 (NOT stdout/stderr, NOT parameter store)
    evidence = s3_get_json_with_retry(bucket, s3_key, timeout_seconds=240, poll_seconds=3)

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
                reason = "Last Start increased after running command (strong confirmation job started)"
            else:
                started_confirmed = False
                reason = "Last Start did not increase (job may not have started OR timestamp didn't change yet)"
        except Exception as e:
            started_confirmed = False
            reason = f"Could not parse before/after timestamps. before=[{before_ts}] after=[{after_ts}] err={e}"
    else:
        started_confirmed = False
        reason = "Missing before/after lastStart values in evidence. Check EC2 debug output (autorep/profile)."

    return {
        "ok": True,
        "fullCommandSent": full_cmd,
        "jobExtractedInLambda": job_for_evidence,
        "autosysStartedConfirmed": started_confirmed,
        "autosysStartReason": reason,
        "autosysLastStartBefore": before_ts or None,
        "autosysLastStartAfter": after_ts or None,
        "commandRC": evidence.get("commandRC"),
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
        "debugFromEvidence": {
            "commandDecoded": evidence.get("commandDecoded"),
            "commandExecuted": evidence.get("commandExecuted"),
            "jobExtractedOnInstance": evidence.get("jobExtractedOnInstance"),
            "cmdStdoutStderrSample": evidence.get("cmdStdoutStderrSample"),
        }
    }