import base64

full_cmd = job_name  # <-- this is your ENTIRE command string from mapping/json
cmd_b64 = base64.b64encode(full_cmd.encode("utf-8")).decode("ascii")

remote_script = f"""#!/bin/bash
set -euo pipefail

CMD_B64="{cmd_b64}"

# Decode exactly what Lambda sent
CMD=$(echo "$CMD_B64" | base64 --decode)

echo "=== CMD received (decoded) ==="
echo "$CMD"
echo "================================"

# Load Autosys profile if present
if [ -f /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh ]; then
  source /export/appl/gv7/gv7dev1/src/DEVL1/GV7-util_scripts/gv7_pysrc/config/infa_autosys_profile.ksh
fi

# Extract JOB name from the *full command* for evidence (autorep needs job, not full command)
JOB=$(echo "$CMD" | awk '
  {{
    for (i=1;i<=NF;i++) {{
      if ($i=="-J") {{ print $(i+1); exit }}
    }}
  }}
')

if [ -z "$JOB" ]; then
  echo "ERROR: Could not extract job name (-J <job>) from CMD"
  exit 2
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
bash -lc "$CMD"
RC=$?
set -e
echo "CMD_RC=$RC"

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
  "commandRC": "$RC",
  "capturedAtUtc": "$NOW_ISO"
}}
EOF

echo "Wrote evidence file: {local_file}"
"""