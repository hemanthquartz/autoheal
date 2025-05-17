- name: Sequential Validation of Each Parsed Index JSON
  run: |
    for file in parsed_indexes/*.json; do
      echo "----------------------------------------"
      echo "Validating $file"
      echo "----------- JSON CONTENT ---------------"
      cat "$file"
      echo "----------- SCHEMA CONTENT ------------"
      cat /tmp/openapi.json
      echo "----------------------------------------"
      python src/scripts/validate_json.py /tmp/openapi.json "$file"
    done