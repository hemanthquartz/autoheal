- name: Create New Indexes
  if: ${{ inputs.select_action == 'add_indexes' }}
  run: |
    echo "Start: Creating new indexes"
    cloudList=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)
    echo "Fetched cloud index list"

    cd $GITHUB_WORKSPACE/indexes

    # Loop through each JSON file
    for indexFile in $(ls *.json); do
      echo "Processing file: ${indexFile}"

      # Check if it's a single object or an array
      isArray=$(jq 'if type=="array" then true else false end' "${indexFile}")

      if [[ "$isArray" == "true" ]]; then
        # Loop over multiple index definitions in a single file
        count=$(jq 'length' "${indexFile}")
        for ((i=0; i<$count; i++)); do
          index=$(jq -c ".[$i]" "${indexFile}")
          indexName=$(echo "$index" | jq -r '.name')

          if [[ "$cloudList" != *"$indexName"* ]]; then
            echo "Creating new index: $indexName"
            curl -X POST "https://${acs}/${stack}/adminconfig/v2/indexes" \
              --header "Authorization: Bearer ${stack_jwt}" \
              --header "Content-Type: application/json" \
              --data-raw "$index"
          else
            echo "Index $indexName already exists. Skipping."
          fi
        done
      else
        # Single index object
        index=$(cat "${indexFile}")
        indexName=$(echo "$index" | jq -r '.name')

        if [[ "$cloudList" != *"$indexName"* ]]; then
          echo "Creating new index: $indexName"
          curl -X POST "https://${acs}/${stack}/adminconfig/v2/indexes" \
            --header "Authorization: Bearer ${stack_jwt}" \
            --header "Content-Type: application/json" \
            --data-raw "$index"
        else
          echo "Index $indexName already exists. Skipping."
        fi
      fi
    done