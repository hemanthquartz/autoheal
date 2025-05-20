name: Manage and Validate Indexes

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Select Splunk Environment'
        required: true
        default: branch_testing
        type: choice
        options:
          - branch_testing
          - branch_apply
      select_action:
        description: 'Select action'
        required: true
        default: add
        type: choice
        options:
          - add_indexes
          - update_indexes

permissions:
  contents: write
  id-token: write

env:
  json_schema: https://admin.splunk.com/service/info/specs/v2/openapi.json

jobs:
  validate_and_manage_indexes:
    runs-on: uhg-runner
    env:
      stack: ${{ secrets.SPLUNK_STACK }}
      stack_jwt: ${{ secrets.SPLUNK_TOKEN }}
      acs: ${{ secrets.SPLUNK_URL }}
    steps:
      - name: Set up Python and Install Dependencies
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          pip install jsonschema jq

      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Download Current Splunk Index Config & Schema
        run: |
          curl "${acs}/${stack}/adminconfig/v2/indexes" \
            --header "Authorization: Bearer ${stack_jwt}" \
            -o /tmp/currentIndexConfiguration.json

          curl -s -o /tmp/openapi.json "${json_schema}"

      - name: Extract Individual Indexes from Multi-Index JSON Files
        run: |
          mkdir -p parsed_indexes
          > parsed_index_list.txt
          for jsonFile in $(ls src/indexes/*.json); do
            jq -c '.[]' "$jsonFile" | nl -nln > temp_index_list.txt
            while read -r line; do
              indexNum=$(echo "$line" | awk '{print $1}')
              indexDef=$(echo "$line" | cut -f2 -d ' ')
              indexPath="parsed_indexes/index_${indexNum}_$(basename $jsonFile)"
              echo "$indexDef" > "$indexPath"
              echo "$indexPath" >> parsed_index_list.txt
            done < temp_index_list.txt
          done

      - name: Validate Each Index JSON Against Schema
        run: |
          for file in parsed_indexes/*.json; do
            python src/scripts/validate_json.py /tmp/openapi.json "$file"
          done

      - name: Validate Index Naming Rules
        run: |
          for file in parsed_indexes/*.json; do
            name=$(jq -r '.name' "$file")
            if [[ "$name" =~ ^_ ]]; then
              echo "[Error] Index '$name' in $file should not start with _"
              exit 1
            fi
            if [[ "$name" =~ [^A-Za-z0-9_]+$ ]]; then
              echo "[Error] Index '$name' in $file contains invalid characters"
              exit 1
            fi
          done

      - name: Create New Indexes
        if: ${{ inputs.select_action == 'add_indexes' }}
        run: |
          echo "Creating new indexes..."
          cloudList=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)
          for indexFile in parsed_indexes/*.json; do
            index=$(jq -r '.name' "$indexFile")
            if [[ ! "${cloudList}" =~ "${index}" ]]; then
              curl -X POST "${acs}/${stack}/adminconfig/v2/indexes" \
                --header "Authorization: Bearer ${stack_jwt}" \
                --header "Content-Type: application/json" \
                --data @"$indexFile"
              sleep 5
              echo "Created: $index"
            else
              echo "[Index exists] Skipping $index"
            fi
          done

      - name: Update Existing Indexes
        if: ${{ inputs.select_action == 'update_indexes' }}
        run: |
          echo "Updating indexes..."
          for indexFile in parsed_indexes/*.json; do
            localIndex=$(cat "$indexFile")
            index=$(echo "$localIndex" | jq -r '.name')
            remoteIndex=$(jq -c --arg name "$index" '.[] | select(.name==$name)' /tmp/currentIndexConfiguration.json)
            if [[ "$(jq --argjson a "$remoteIndex" --argjson b "$localIndex" '$a == $b' <<< '{}')" == "true" ]]; then
              echo "[$index] No update required"
              continue
            fi

            echo "[$index] Updating to reflect Git"
            jsonUpdate=$(echo '{}' | jq '.')
            for indexVar in $(echo "$localIndex" | jq 'del(.name) | del(.datatype)' | jq -r 'keys[]'); do
              localVal=$(echo "$localIndex" | jq -r ".${indexVar}")
              remoteVal=$(echo "$remoteIndex" | jq -r ".${indexVar}")
              if [[ "$localVal" != "$remoteVal" ]]; then
                if [[ "$localVal" =~ ^[0-9]+$ ]]; then
                  jsonUpdate=$(echo "$jsonUpdate" | jq --arg key "$indexVar" --argjson val "$localVal" '. + {($key): $val}')
                else
                  jsonUpdate=$(echo "$jsonUpdate" | jq --arg key "$indexVar" --arg val "$localVal" '. + {($key): $val}')
                fi
              fi
            done

            curl -X PATCH "${acs}/${stack}/adminconfig/v2/indexes/${index}" \
              --header "Authorization: Bearer ${stack_jwt}" \
              --header "Content-Type: application/json" \
              --data "$jsonUpdate"
            echo "[$index] Update complete"
          done