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
  gather_and_validate_indexes:
    if: ${{ inputs.component == 'indexes' }}
    runs-on: ubuntu-latest

    steps:
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install jsonschema jq

      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Download Splunk OpenAPI Schema
        run: |
          curl -s -o /tmp/openapi.json "${{ env.json_schema }}"

      - name: Extract Individual Indexes from Multi-Index JSON Files
        id: extract_indexes
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

      - name: Sequential Validation of Each Parsed Index JSON
        run: |
          echo "Starting sequential validation..."
          while IFS= read -r file; do
            echo "Validating $file"

            python3 <<EOF
import json
import sys
from jsonschema import validate, ValidationError

with open("$file") as f:
    data = json.load(f)

with open("/tmp/openapi.json") as s:
    schema = json.load(s)

try:
    validate(instance=data, schema=schema)
except ValidationError as e:
    print(f"[SCHEMA ERROR] in $file: {e.message}")
    sys.exit(1)

# Name validation
index_name = data.get("name", "")
import re
if index_name.startswith("_"):
    print(f"[NAMING ERROR] in $file: index name cannot start with underscore")
    sys.exit(1)

if not re.match(r"^[A-Za-z0-9._-]+$", index_name):
    print(f"[NAMING ERROR] in $file: index name contains invalid characters")
    sys.exit(1)

print(f"[PASS] $file passed all validations.")
EOF

          done < parsed_index_list.txt