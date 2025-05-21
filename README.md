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
    runs-on: ubuntu-latest
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

      - name: Download Current Index Configuration and Schema
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

      - name: Gather Changed Indexes
        id: gather_changed
        uses: tj-actions/changed-files@v35
        with:
          json: true
          quotepaths: false
          files: |
            parsed_indexes/*.json

      - name: Filter Only Changed Index Files
        id: filter_indexes
        if: steps.gather_changed.outputs.any_changed == 'true'
        run: |
          matrix=$(jq -n --argjson files "${{ steps.gather_changed.outputs.all_changed_files }}" '$files')
          echo "matrix=${matrix}" >> $GITHUB_OUTPUT

      - name: Validate Changed Indexes
        if: steps.gather_changed.outputs.any_changed == 'true'
        run: |
          for file in ${{ join(fromJSON(steps.filter_indexes.outputs.matrix), ' ') }}; do
            echo "Validating $file"
            python src/scripts/validate_json.py /tmp/openapi.json "$file"
          done

      - name: Validate Naming Rules
        if: steps.gather_changed.outputs.any_changed == 'true'
        run: |
          for file in ${{ join(fromJSON(steps.filter_indexes.outputs.matrix), ' ') }}; do
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

      - name: Create or Update Changed Indexes
        if: steps.gather_changed.outputs.any_changed == 'true'
        run: |
          for file in ${{ join(fromJSON(steps.filter_indexes.outputs.matrix), ' ') }}; do
            index=$(jq -r '.name' "$file")
            existing=$(jq -c --arg index "$index" '.[] | select(.name==$index)' /tmp/currentIndexConfiguration.json)

            if [[ -z "$existing" ]]; then
              echo "Creating new index: $index"
              curl -X POST "${acs}/${stack}/adminconfig/v2/indexes" \
                --header "Authorization: Bearer ${stack_jwt}" \
                --header "Content-Type: application/json" \
                --data @"$file"
            else
              echo "Evaluating update for $index"
              localVal=$(cat "$file")
              isSame=$(jq --argjson a "$existing" --argjson b "$localVal" '$a == $b' <<< '{}')

              if [[ "$isSame" == "true" ]]; then
                echo "[$index] No update required"
              else
                echo "Updating index: $index"
                patch=$(echo '{}' | jq '.')
                for key in $(jq -r 'keys[]' "$file"); do
                  newVal=$(jq -r ".${key}" "$file")
                  oldVal=$(echo "$existing" | jq -r ".${key}")
                  if [[ "$newVal" != "$oldVal" ]]; then
                    if [[ "$newVal" =~ ^[0-9]+$ ]]; then
                      patch=$(echo "$patch" | jq --arg key "$key" --argjson val "$newVal" '. + {($key): $val}')
                    else
                      patch=$(echo "$patch" | jq --arg key "$key" --arg val "$newVal" '. + {($key): $val}')
                    fi
                  fi
                done

                curl -X PATCH "${acs}/${stack}/adminconfig/v2/indexes/${index}" \
                  --header "Authorization: Bearer ${stack_jwt}" \
                  --header "Content-Type: application/json" \
                  --data "$patch"
              fi
            fi
          done