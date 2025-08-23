name: "Splunk HEC Uploader"
description: "Uploads log chunks to Splunk HEC with retries and metadata"

inputs:
  hec_url:
    description: "Base HEC URL, e.g. https://splunk.example.com:8088"
    required: true
  hec_token:
    description: "Splunk HEC token"
    required: true
  index:
    description: "Splunk index"
    required: false
    default: "main"
  source:
    description: "Splunk source"
    required: false
    default: "github:actions"
  sourcetype:
    description: "Splunk sourcetype"
    required: false
    default: "github:actions:run"
  host:
    description: "Host field in Splunk"
    required: false
    default: "github"
  verify_tls:
    description: "Set to 'false' to skip TLS verification"
    required: false
    default: "true"
  chunks_dir:
    description: "Directory containing split log parts (e.g., chunks/part_*)"
    required: true
  run_json:
    description: "GitHub Actions run metadata JSON (stringified)"
    required: true

runs:
  using: "composite"
  steps:
    - name: Upload chunks to Splunk HEC
      shell: bash
      env:
        HEC_URL: ${{ inputs.hec_url }}
        HEC_TOKEN: ${{ inputs.hec_token }}
        INDEX: ${{ inputs.index }}
        SOURCE: ${{ inputs.source }}
        STYPE: ${{ inputs.sourcetype }}
        HOST: ${{ inputs.host }}
        VERIFY_TLS: ${{ inputs.verify_tls }}
        CHUNKS_DIR: ${{ inputs.chunks_dir }}
        RUN_JSON: ${{ inputs.run_json }}
      run: |
        set -euo pipefail

        # Ensure jq is present (ubuntu-latest usually has it; if not, fail clearly)
        if ! command -v jq >/dev/null 2>&1; then
          echo "ERROR: 'jq' is required by this action. Install it earlier in your workflow."
          exit 1
        fi

        if [ ! -d "$CHUNKS_DIR" ]; then
          echo "No chunks directory found at '$CHUNKS_DIR'; nothing to send."
          exit 0
        fi

        # Pull a few fields from the run metadata for Splunk-enrichment
        REPO=$(echo "$RUN_JSON" | jq -r '.repository.full_name // .repository.name // "unknown"')
        WORKFLOW_NAME=$(echo "$RUN_JSON" | jq -r '.name // "unknown_workflow"')
        RUN_ID=$(echo "$RUN_JSON" | jq -r '.id // "0"')
        RUN_ATTEMPT=$(echo "$RUN_JSON" | jq -r '.run_attempt // 1')
        CONCLUSION=$(echo "$RUN_JSON" | jq -r '.conclusion // "unknown"')

        CURL_FLAGS=( -sS --retry 5 --retry-delay 2 --retry-connrefused -H "Authorization: Splunk ${HEC_TOKEN}" -H "Content-Type: application/json" )
        if [ "$VERIFY_TLS" != "true" ]; then
          CURL_FLAGS+=( -k )
        fi

        ENDPOINT="${HEC_URL%/}/services/collector/event"

        shopt -s nullglob
        sent=0
        for f in "$CHUNKS_DIR"/part_*; do
          # Encode the chunk text as a JSON string
          CONTENT=$(jq -Rs . < "$f")

          # Build HEC payload with metadata
          PAYLOAD=$(jq -n \
            --arg host "$HOST" \
            --arg src  "$SOURCE" \
            --arg st   "$STYPE" \
            --arg idx  "$INDEX" \
            --arg repo "$REPO" \
            --arg wf   "$WORKFLOW_NAME" \
            --arg rid  "$RUN_ID" \
            --arg ra   "$RUN_ATTEMPT" \
            --arg concl "$CONCLUSION" \
            --arg t "$(date +%s)" \
            --argjson content "$CONTENT" '
            {
              time: ($t|tonumber),
              host: $host,
              source: $src,
              sourcetype: $st,
              index: $idx,
              event: "github_actions_log",
              fields: {
                repository: $repo,
                workflow: $wf,
                run_id: $rid,
                run_attempt: $ra,
                conclusion: $concl
              },
              event: { body: $content }
            }
          ')

          HTTP_CODE=$(curl "${CURL_FLAGS[@]}" -w "%{http_code}" -o /tmp/resp.json -X POST "$ENDPOINT" --data "$PAYLOAD" || true)
          if [ "$HTTP_CODE" != "200" ]; then
            echo "HEC post failed for chunk '$f' (HTTP $HTTP_CODE). Response:"
            cat /tmp/resp.json || true
            exit 1
          fi
          sent=$((sent+1))
        done

        echo "Uploaded $sent chunk(s) to Splunk HEC successfully."