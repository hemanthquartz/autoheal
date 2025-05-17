name: Component Validation

on:
  workflow_call:
    inputs:
      component:
        required: true
        type: string

env:
  json_schema: https://admin.splunk.com/service/info/specs/v2/openapi.json

jobs:
  gather_changed_indexes:
    if: ${{ inputs.component == 'indexes' }}
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
    steps:
      - name: Install jq
        run: sudo apt install -y jq

      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Detect Changed Index Files
        id: changed-files
        uses: tj-actions/changed-files@v35
        with:
          json: true
          quotepath: false
          files: |
            indexes/*.json

      - name: Extract Individual Indexes From Multi-Index JSON Files
        if: steps.changed-files.outputs.any_changed == 'true'
        id: extract-indexes
        run: |
          mkdir -p parsed_indexes
          > parsed_index_list.txt

          for jsonFile in $(ls indexes/*.json); do
            echo "Parsing file: $jsonFile"
            jq -c '.[]' "$jsonFile" | nl -nln > temp_index_list.txt

            while read -r line; do
              indexNum=$(echo "$line" | awk '{print $1}')
              indexDef=$(echo "$line" | cut -f2-)
              indexPath="parsed_indexes/index_${indexNum}_$(basename $jsonFile)"
              echo "$indexDef" > "$indexPath"
              echo "$indexPath" >> parsed_index_list.txt
            done < temp_index_list.txt
          done

      - name: Set Output Matrix
        id: set-matrix
        run: |
          indexes=$(jq -R -s -c 'split("\n") | map(select(. != ""))' parsed_index_list.txt)
          echo "matrix={\"index\":${indexes}}" >> "$GITHUB_OUTPUT"

  validate_changed_indexes:
    if: ${{ needs.gather_changed_indexes.outputs.matrix != '[]' && needs.gather_changed_indexes.outputs.matrix != '' }}
    needs: gather_changed_indexes
    strategy:
      matrix: ${{ fromJSON(needs.gather_changed_indexes.outputs.matrix) }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v3

      - name: Download OpenAPI Schema
        id: prepare-schema
        run: |
          curl -s -o /tmp/openapi.json ${{ env.json_schema }}

      - name: Validate JSON Schema
        uses: docker://orrosenblatt/validate-json-action:latest
        env:
          INPUT_SCHEMA: /tmp/openapi.json
          INPUT_JSONS: ${{ matrix.index }}

      - name: Validate Index Does Not Start with Underscore
        run: |
          if [[ $(cat ${{ matrix.index }} | jq -r '.name' | grep "^_") ]]; then
            echo "[ERROR] - Index name starts with underscore"
            exit 1
          fi

      - name: Validate Index Name Characters
        run: |
          if [[ ! $(cat ${{ matrix.index }} | jq -r '.name' | grep -E "^[A-Za-z0-9._-]+$") ]]; then
            echo "[ERROR] - Invalid characters in index name"
            exit 1
          fi






name: Manage Indexes

on:
  workflow_dispatch:
    inputs:
      environment:
        description: Select Splunk Environment
        required: true
        default: branch_testing
        type: choice
        options:
          - branch_testing
          - branch_apply
      select_action:
        description: Select action
        required: true
        default: add
        type: choice
        options:
          - add_indexes
          - update_indexes

jobs:
  validate_indexes_component:
    uses: ./.github/workflows/splunkcloud-component-validation.yaml
    with:
      component: indexes

  ManageIndexes:
    needs: validate_indexes_component
    runs-on: ubuntu-latest
    env:
      stack: ${{ secrets.SPLUNK_STACK }}
      stack_jwt: ${{ secrets.SPLUNK_TOKEN }}
      acs: ${{ secrets.SPLUNK_URL }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Perform Splunk list action
        run: |
          API_PATH="/adminconfig/v2/indexes"
          curl "https://${acs}/${stack}${API_PATH}" \
            --header "Authorization: Bearer ${stack_jwt}" \
            -o /tmp/currentIndexConfiguration.json

      - name: Upload Current Index Configuration
        uses: actions/upload-artifact@v4
        with:
          name: currentIndexConfiguration.json
          path: /tmp/currentIndexConfiguration.json
          retention-days: 5

      # KEEP ALL EXISTING INDEX LOGIC UNCHANGED HERE
      # Including parsing, creation, update, and status checks
