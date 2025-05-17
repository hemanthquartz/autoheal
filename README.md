import json
import sys
from jsonschema import validate, ValidationError

def main(schema_file, json_file):
    with open(schema_file) as sf, open(json_file) as jf:
        schema = json.load(sf)
        data = json.load(jf)

    try:
        validate(instance=data, schema=schema)
        print("✅ Validation successful.")
    except ValidationError as e:
        print(f"❌ Validation failed: {e.message}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: validate_json.py <schema_file> <json_file>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])




name: Validate JSON

on:
  pull_request:
    paths:
      - 'indexes/*.json'
      - '.github/schemas/**'

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install jsonschema

      - name: Validate each JSON file
        run: |
          for file in indexes/*.json; do
            echo "Validating $file"
            python .github/scripts/validate_json.py .github/schemas/index-schema.json "$file"
          done





