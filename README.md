Got it—here’s a clean, modular setup to forward any GitHub Actions run logs to Splunk via HEC. It uses:
	•	a repository-wide listener (workflow_run) that triggers when any workflow completes
	•	a reusable workflow you can also call manually or from other workflows
	•	a tiny composite action that posts chunks to your Splunk HEC endpoint with retries

You can drop these files into your repo as-is.

⸻

1) Auto-forward all run logs to Splunk

File: .github/workflows/forward-logs-to-splunk.yml

name: Forward Actions Logs to Splunk

on:
  workflow_run:
    workflows: ["*"]        # listen to all workflows
    types: [completed]

permissions:
  actions: read     # required to download logs
  contents: read

concurrency:
  group: forward-logs-to-splunk-${{ github.event.workflow_run.id }}
  cancel-in-progress: false

jobs:
  forward:
    uses: ./.github/workflows/send-logs-to-splunk.yml
    secrets:
      hec_token: ${{ secrets.SPLUNK_HEC_TOKEN }}
    with:
      hec_url: ${{ secrets.SPLUNK_HEC_URL }}                 # e.g. https://splunk.company.com:8088
      index:   ${{ secrets.SPLUNK_INDEX || 'main' }}
      source:  github:actions
      sourcetype: github:actions:run
      host:    ${{ github.repository_owner }}
      verify_tls: true
      # pass run metadata from the workflow_run event
      run_id:  ${{ github.event.workflow_run.id }}
      repo:    ${{ github.event.workflow_run.repository.name }}
      owner:   ${{ github.event.workflow_run.repository.owner.login }}

Secrets to set (Repo or Org):
	•	SPLUNK_HEC_URL (example: https://splunk.example.com:8088)
	•	SPLUNK_HEC_TOKEN
	•	(Optional) SPLUNK_INDEX

⸻

2) Reusable workflow (download + chunk + send)

File: .github/workflows/send-logs-to-splunk.yml

name: Send Logs to Splunk (Reusable)

on:
  workflow_call:
    inputs:
      hec_url:
        type: string
        required: true
      index:
        type: string
        required: false
        default: main
      source:
        type: string
        required: false
        default: github:actions
      sourcetype:
        type: string
        required: false
        default: github:actions:run
      host:
        type: string
        required: false
        default: github
      verify_tls:
        type: boolean
        required: false
        default: true
      run_id:
        type: string
        required: true
      repo:
        type: string
        required: true
      owner:
        type: string
        required: true
    secrets:
      hec_token:
        required: true

permissions:
  actions: read
  contents: read

jobs:
  ship:
    runs-on: ubuntu-latest
    steps:
      - name: Prep tools
        run: |
          sudo apt-get update -y
          sudo apt-get install -y jq unzip

      - name: Download run metadata
        id: meta
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          curl -sSfL \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/${{ inputs.owner }}/${{ inputs.repo }}/actions/runs/${{ inputs.run_id }}" \
            -o run.json

          echo "run_json=$(jq -c . run.json)" >> "$GITHUB_OUTPUT"

      - name: Download logs zip
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          mkdir -p logs
          curl -sSfL \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/zip" \
            "https://api.github.com/repos/${{ inputs.owner }}/${{ inputs.repo }}/actions/runs/${{ inputs.run_id }}/logs" \
            -o logs.zip
          unzip -q logs.zip -d logs
          # create one combined text
          find logs -type f -name "*.txt" -print0 \
            | xargs -0 -I{} sh -c 'echo -e "\n===== FILE: {} =====\n"; cat "{}"' \
            > combined.log

      - name: Split into ~900KB chunks
        run: |
          mkdir -p chunks
          # Avoid too-large payloads; Splunk HEC default maxEventSize is typically 1MB
          split -b 900k -d -a 4 combined.log chunks/part_

      - name: Post chunks to Splunk HEC
        uses: ./.github/actions/splunk-hec-upload
        with:
          hec_url:  ${{ inputs.hec_url }}
          hec_token: ${{ secrets.hec_token }}
          index:    ${{ inputs.index }}
          source:   ${{ inputs.source }}
          sourcetype: ${{ inputs.sourcetype }}
          host:     ${{ inputs.host }}
          verify_tls: ${{ inputs.verify_tls }}
          chunks_dir: chunks
          run_json: ${{ steps.meta.outputs.run_json }}


⸻

3) Composite action: robust HEC uploader

File: .github/actions/splunk-hec-upload/action.yml

name: "Splunk HEC Uploader"
description: "Uploads log chunks to Splunk HEC with retries and metadata"
inputs:
  hec_url:
    required: true
  hec_token:
    required: true
  index:
    required: false
    default: main
  source:
    required: false
    default: github:actions
  sourcetype:
    required: false
    default: github:actions:run
  host:
    required: false
    default: github
  verify_tls:
    required: false
    default: "true"
  chunks_dir:
    required: true
  run_json:
    required: true
runs:
  using: "composite"
  steps:
    - shell: bash
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

        if [ ! -d "$CHUNKS_DIR" ]; then
          echo "No chunks directory found; nothing to send."
          exit 0
        fi

        # Extract a few useful fields from the run for Splunk-enriching fields
        REPO=$(echo "$RUN_JSON" | jq -r '.repository.full_name')
        WORKFLOW_NAME=$(echo "$RUN_JSON" | jq -r '.name')
        RUN_ID=$(echo "$RUN_JSON" | jq -r '.id')
        RUN_ATTEMPT=$(echo "$RUN_JSON" | jq -r '.run_attempt // 1')
        CONCLUSION=$(echo "$RUN_JSON" | jq -r '.conclusion')
        EVENT_TIME=$(date +%s)

        CURL_FLAGS=( -sS --retry 5 --retry-delay 2 --retry-connrefused )
        if [ "$VERIFY_TLS" != "true" ]; then
          CURL_FLAGS+=( -k )
        fi

        ENDPOINT="$HEC_URL/services/collector/event"

        # Send each chunk as one HEC event (multiline body)
        shopt -s nullglob
        for f in "$CHUNKS_DIR"/part_*; do
          # Escape chunk content for JSON
          CONTENT=$(python3 - <<'PY'
import json,sys
print(json.dumps({"body": open(sys.argv[1],"r",errors="ignore").read()}))
PY
"$f")

          # Merge with HEC envelope + Splunk metadata fields
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
            --argjson content "$CONTENT" \
            --arg time "$(date +%s)" '
            {
              time: ($time|tonumber),
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
              }
            } * { event: $content }
          ')

          # Post
          HTTP_CODE=$(curl "${CURL_FLAGS[@]}" \
            -H "Authorization: Splunk ${HEC_TOKEN}" \
            -H "Content-Type: application/json" \
            -w "%{http_code}" -o /tmp/resp.json \
            -X POST "$ENDPOINT" \
            --data "$PAYLOAD" || true)

          if [ "$HTTP_CODE" != "200" ]; then
            echo "HEC post failed for $f (HTTP $HTTP_CODE). Response:"
            cat /tmp/resp.json || true
            exit 1
          fi
        done
        echo "All chunks sent to Splunk successfully."


⸻

How it works
	•	When any workflow completes, GitHub fires workflow_run.
	•	The listener calls the reusable workflow, which:
	1.	Downloads the logs zip for that run via GitHub API.
	2.	Unzips & concatenates into one file.
	3.	Splits into ~900KB chunks (safe for common HEC max event sizes).
	4.	Uses the composite action to POST each chunk to /services/collector/event with metadata (repo, workflow name, run id, attempt, conclusion, etc.).
	•	Set verify_tls: false if you’re using a lab Splunk with a self-signed cert.

⸻

Quick validation in Splunk

In Splunk Search, try:

index=main sourcetype=github:actions:run source=github:actions
| stats count by repository, workflow, conclusion

Or to see raw lines (chunk bodies are in event.body):

index=main sourcetype=github:actions:run
| eval text=mvjoinspath(event.body,"")
| table _time repository workflow run_id run_attempt conclusion text


⸻

Notes & options
	•	HEC source/index/sourcetype are configurable per repo/org. Use org secrets if you want this for many repos.
	•	If your Splunk admin prefers the /raw endpoint, this design can be trivially switched—but /event with metadata fields is usually nicer for search.
	•	If a single repo generates very large logs, you can tighten chunk size (split -b 600k) or enable HEC token-assigned indexes only.

If you want, I can tailor the sourcetype/fields to match your Splunk CIM or a specific index naming scheme you already use.