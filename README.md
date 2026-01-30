def build_debug_autosys_command(job_name: str) -> str:
    """
    IMPORTANT: This must contain ZERO single quotes because the SSM document wraps {{ command }}
    inside: bash -c 'source ...; {{ command }}'
    """
    # Escape only double-quotes and backslashes so we can safely wrap in "..."
    j = (job_name or "").replace("\\", "\\\\").replace('"', '\\"')

    cmd = f"""
echo "__AUTOSYS_DEBUG_BEGIN__" 2>&1
date -Is 2>&1
echo "JOB={j}" 2>&1
echo "WHOAMI=$(whoami)" 2>&1
echo "HOST=$(hostname)" 2>&1
echo "PWD=$(pwd)" 2>&1
echo "PATH=$PATH" 2>&1

echo "__CHECK_BINARIES__" 2>&1
command -v sendevent 2>&1 || echo "MISSING:sendevent" 2>&1
command -v autostatus 2>&1 || echo "MISSING:autostatus" 2>&1
command -v autorep 2>&1 || echo "MISSING:autorep" 2>&1

echo "__STEP_SENDEVENT__" 2>&1
SE_OUT=$(sendevent -E FORCE_STARTJOB -J "{j}" 2>&1)
SE_RC=$?
echo "SENDEVENT_RC=$SE_RC" 2>&1
echo "SENDEVENT_OUTPUT=$SE_OUT" 2>&1

echo "__STEP_SLEEP__" 2>&1
sleep 5

echo "__STEP_AUTOSTATUS__" 2>&1
AS_OUT=$(autostatus -J "{j}" 2>&1)
AS_RC=$?
echo "AUTOSTATUS_RC=$AS_RC" 2>&1
echo "AUTOSTATUS_OUTPUT=$AS_OUT" 2>&1

echo "__STEP_AUTOREP__" 2>&1
AR_OUT=$(autorep -J "{j}" -q 2>&1)
AR_RC=$?
echo "AUTOREP_RC=$AR_RC" 2>&1
echo "AUTOREP_OUTPUT=$AR_OUT" 2>&1

echo "__START_CONFIRMATION_CHECK__" 2>&1
START=NO
if [ "$SE_RC" -eq 0 ]; then START=YES; fi
echo "$AS_OUT" | egrep -qi "(RUN|RUNNING|START|STARTING|ACTIVE|EXEC|EXECUTING|IN[_ ]PROGRESS|ACTIVATED)" && START=YES
echo "START_CONFIRMED=$START" 2>&1

echo "__AUTOSYS_DEBUG_END__" 2>&1
"""
    return " ".join(line.strip() for line in cmd.splitlines() if line.strip())