jobs:
  capture_logs:
    name: Capture Logs if aicicd Fails
    needs: [aicicd]
    if: failure()  # Run only if aicicd fails
    runs-on: uhg-runner
    env:
      GH_TOKEN: ${{ secrets.PDE_GHEC_PAT_SECRET }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Fetch Workflow Logs
        run: |
          mkdir -p logs
          echo "Fetching logs from aicicd..."
          gh run view ${{ github.run_id }} --log > logs/aicicd_error_log.txt || echo "Error log capture failed."
          
          # Print error before uploading
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
