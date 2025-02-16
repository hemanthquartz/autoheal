      - name: Get Workflow Run Jobs (Failed Only)
        run: |
          FAILED_JOBS=$(gh api repos/${{ github.repository }}/actions/runs/${{ github.run_id }}/jobs --jq '.jobs[] | select(.conclusion=="failure") | "\(.id) \(.name)"')
          
          echo "FAILED_JOBS<<EOF" >> $GITHUB_ENV
          echo "$FAILED_JOBS" >> $GITHUB_ENV
          echo "EOF" >> $GITHUB_ENV

          echo "Captured Failed Job Details:"
          echo "$FAILED_JOBS"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Debug Failed Job Details
        run: |
          echo "Failed Jobs Retrieved:"
          echo "$FAILED_JOBS"

      - name: Fetch and Extract Errors from Logs
        run: |
          echo "Extracting errors from failed job logs..." > errors.log
          
          while IFS= read -r line; do
            JOB_ID=$(echo $line | awk '{print $1}')
            JOB_NAME=$(echo $line | awk '{print substr($0, index($0,$2))}')
            
            echo "Fetching logs for Job ID: $JOB_ID, Job Name: $JOB_NAME"
            
            gh api repos/${{ github.repository }}/actions/jobs/${JOB_ID}/logs > job_${JOB_ID}.log
            
            # Extract multi-line errors
            awk '
              /Error:/ {print "\n"$0; capturing=1; next}
              capturing && /^[[:space:]]*$/ {capturing=0; next}
              capturing {print $0}
            ' job_${JOB_ID}.log >> errors.log || echo "No errors found for $JOB_NAME"

          done <<< "$FAILED_JOBS"

          echo "Extracted Errors:"
          cat errors.log
