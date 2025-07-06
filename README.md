- name: Extract Index Names from Multi-Index JSON Files
  id: extract_indexes
  run: |
    echo "Extracting index definitions from multiple JSON files..."
    mkdir -p parsed_indexes

    for jsonFile in $(ls $GITHUB_WORKSPACE/src/indexes/*.json); do
      echo "Parsing file: $jsonFile"

      jq -c '.[]' "$jsonFile" | while read -r line; do
        indexName=$(echo "$line" | jq -r '.name')
        echo "Extracting index: $indexName from $jsonFile"
        echo "$line" > parsed_indexes/${indexName}.json
      done
    done

    echo "Exported indexes:"
    ls parsed_indexes
  shell: bash