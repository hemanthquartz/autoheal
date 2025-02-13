
  capture_logs:
    name: Capture Logs if aicicd Fails
    needs: [aicicd]  # Ensures it runs after aicicd
    if: failure()  # Run only if aicicd fails
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Install GitHub CLI (if not available)
        run: |
          if ! command -v gh &> /dev/null; then
            sudo apt update && sudo apt install -y gh
          fi

      - name: Wait Until Logs Are Available
        run: |
          echo "Waiting for logs from aicicd..."
          for i in {1..10}; do
            LOG_OUTPUT=$(gh run view ${{ github.run_id }} --log || echo "pending")
            if [[ "$LOG_OUTPUT" != "pending" ]]; then
              echo "$LOG_OUTPUT" > logs/aicicd_error_log.txt
              break
            fi
            echo "Logs not available yet... retrying in 10 seconds"
            sleep 10
          done

      - name: Print Logs Before Uploading
        run: |
          echo "========== START OF AICICD ERROR LOG =========="
          cat logs/aicicd_error_log.txt || echo "No logs captured."
          echo "=========== END OF AICICD ERROR LOG ==========="

      - name: Upload Logs as Artifact
        uses: actions/upload-artifact@v4
        with:
          name: aicicd-error-log
          path: logs/aicicd_error_log.txt



  capture_logs:
    name: Capture Logs if aicicd Fails
    needs: [aicicd]
    if: failure()  # Run only if aicicd fails
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Capture Logs Using mathiasvr/command-output
        id: fetch_logs
        uses: mathiasvr/command-output@v2.0.0
        with:
          run: |
            mkdir -p logs
            gh run view ${{ github.run_id }} --log > logs/aicicd_error_log.txt || echo "Error log capture failed."

      - name: Print Captured Logs
        run: |
          echo "========== START OF CAPTURED LOGS =========="
          cat logs/aicicd_error_log.txt || echo "No logs captured."
          echo "=========== END OF CAPTURED LOGS ==========="

      - name: Upload Logs as Artifact
        uses: actions/upload-artifact@v4
        with:
          name: aicicd-error-log
          path: logs/aicicd_error_log.txt



  capture_backend_logs:
    name: Capture Backend Logs
    needs: [aicicd]
    if: failure()  # Run only if aicicd fails
    runs-on: ubuntu-latest
    steps:
      - name: Download Backend Logs
        run: |
          mkdir -p logs
          echo "Fetching logs from backend service..."
          ssh user@backend-server "cat /var/log/backend-service.log" > logs/backend_error_log.txt
          echo "Logs fetched successfully."

      - name: Print Logs Before Uploading
        run: |
          echo "========== START OF BACKEND ERROR LOG =========="
          cat logs/backend_error_log.txt || echo "No logs found."
          echo "=========== END OF BACKEND ERROR LOG ==========="

      - name: Upload Backend Error Logs
        uses: actions/upload-artifact@v4
        with:
          name: backend-error-log
          path: logs/backend_error_log.txt




#!/bin/bash

echo "Fetching logs from the failed 'aicicd' job..."

# Get the run ID of the most recent workflow
RUN_ID=$(gh run list --workflow="${GITHUB_WORKFLOW}" --limit 1 --json databaseId --jq '.[0].databaseId')

if [[ -z "$RUN_ID" ]]; then
  echo "Error: Could not find a recent run for this workflow!"
  exit 1
fi

echo "Run ID: $RUN_ID"

# Get the job ID for `aicicd`
JOB_ID=$(gh run view $RUN_ID --json jobs | jq -r '.jobs[] | select(.name | contains("aicicd")) | .id')

if [[ -z "$JOB_ID" || "$JOB_ID" == "null" ]]; then
  echo "Error: Could not find job ID for aicicd!"
  exit 1
fi

echo "Job ID: $JOB_ID"

# Fetch the logs for the `aicicd` job
gh run view $RUN_ID --job $JOB_ID --log > logs/aicicd_error_log.txt || echo "Error log capture failed."

# Print error log before uploading
if [[ -s logs/aicicd_error_log.txt ]]; then
  echo "========== START OF ERROR LOG =========="
  cat logs/aicicd_error_log.txt
  echo "=========== END OF ERROR LOG ==========="
else
  echo "No errors captured in the log."
fi
JOB_ID=$(gh run view $RUN_ID --log | grep -Eo '"id":[0-9]+' | awk -F: '{print $2}' | head -1)

jobs:
  capture_logs:
    name: Capture Logs if aicicd Fails
    needs: [aicicd]
    if: failure()  # Run only if aicicd fails
    runs-on: uhg-runner
    env:
      GH_TOKEN: ${{ secrets.PDE_GHEC_PAT_SECRET }}  # Use the correct token
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Fetch Workflow Logs for aicicd
        run: |
          mkdir -p logs
          echo "Fetching logs from the failed 'aicicd' job..."
          
          # Get the run ID of the workflow
          RUN_ID=${{ github.run_id }}

          # Get the job ID for `aicicd`
          JOB_ID=$(gh run view $RUN_ID --json jobs | jq -r '.jobs[] | select(.name=="aicicd-poc") | .id')

          if [[ -z "$JOB_ID" ]]; then
            echo "Error: Could not find job ID for aicicd!"
            exit 1
          fi

          # Fetch the logs for the `aicicd` job
          gh run job-view $JOB_ID --log > logs/aicicd_error_log.txt || echo "Error log capture failed."

          # Print error log before uploading
          if [[ -s logs/aicicd_error_log.txt ]]; then
            echo "========== START OF ERROR LOG =========="
            cat logs/aicicd_error_log.txt
            echo "=========== END OF ERROR LOG ==========="
          else
            echo "No errors captured in the log."
          fi

      - name: Upload Error Logs
        uses: actions/upload-artifact@v4
        with:
          name: aicicd-error-log
          path: logs/aicicd_error_log.txt
