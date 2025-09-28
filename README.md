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