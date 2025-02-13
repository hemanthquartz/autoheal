
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
