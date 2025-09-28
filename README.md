import re
import subprocess
import datetime
import time
import logging

def wait_for_task_completion(task_name, poll_interval=5, timeout=900):
    """Polls the scheduled task status until it is NOT 'Running' or until timeout."""
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout)

    while datetime.datetime.now() < end_time:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", task_name, "/fo", "LIST", "/v"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logging.error(f"Failed to query task '{task_name}': {result.stderr.strip()}")
            return False

        output = result.stdout
        # Extract just the Status field (avoid matches like 'stop if still running')
        m = re.search(r"(?mi)^\s*Status:\s*(.+?)\s*$", output)
        status = m.group(1).strip().lower() if m else None

        if not status:
            logging.warning(f"Couldn't find Status for task '{task_name}'. Raw output:\n{output}")
            time.sleep(poll_interval)
            continue

        if status != "running":
            logging.info(f"Scheduled task '{task_name}' status is '{status}'. Treating as completed/not running.")
            return True

        logging.info(f"Scheduled task '{task_name}' is still running...")
        time.sleep(poll_interval)

    logging.warning(f"Scheduled task '{task_name}' did not complete within timeout ({timeout} seconds).")
    return False







import subprocess
import logging

def run_verimove():
    verimove_exe = r"K:\Precisely\Verimove\mu.exe"
    job_name = "samplejob"
    def_file = r"C:\data\add_mass\addressmaster_tcs.def"

    command = [verimove_exe, job_name, def_file]

    logging.info("Running Verimove command: %s", " ".join(command))

    try:
        result = subprocess.run(command, capture_output=True, text=True)

        if result.returncode == 0:
            logging.info("Verimove job completed successfully.")
            logging.info("STDOUT: %s", result.stdout.strip())
        else:
            logging.error("Verimove job failed with exit code %s", result.returncode)
            logging.error("STDOUT: %s", result.stdout.strip())
            logging.error("STDERR: %s", result.stderr.strip())

    except Exception as e:
        logging.exception("Error while running Verimove job: %s", str(e))




import subprocess
import logging

def run_verimove():
    batch_file = r"C:\data\add_mass\address_mast.bat"   # full path to your .bat file

    logging.info("Running Verimove batch file: %s", batch_file)

    try:
        # run batch file
        result = subprocess.run(batch_file, capture_output=True, text=True, shell=True)

        if result.returncode == 0:
            logging.info("Verimove batch completed successfully.")
            logging.info("STDOUT: %s", result.stdout.strip())
        else:
            logging.error("Verimove batch failed with exit code %s", result.returncode)
            logging.error("STDOUT: %s", result.stdout.strip())
            logging.error("STDERR: %s", result.stderr.strip())

    except Exception as e:
        logging.exception("Error while running Verimove batch: %s", str(e))



"commands": [
  "if (Test-Path 'D:\\VeriMove\\Input') { & 'C:\\Program Files\\Python311\\python.exe' 'C:\\data\\add_mass\\schedular\\add_mass_E2E.py'; exit 0 } else { exit 1 }"
]


