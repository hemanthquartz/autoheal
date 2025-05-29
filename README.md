- name: Delete Orphaned Indexes from Splunk Cloud
  if: always()
  run: |
    echo "Fetching local index names from parsed files..."
    localIndexes=""
    for file in parsed_indexes/*; do
      index=$(jq -r '.name' "$file")
      localIndexes="$localIndexes $index"
    done

    echo "Local indexes: $localIndexes"

    echo "Fetching current indexes from Splunk Cloud..."
    cloudIndexes=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)

    echo "Comparing and deleting orphaned indexes..."
    for cloudIndex in $cloudIndexes; do
      found=false
      for localIndex in $localIndexes; do
        if [[ "$cloudIndex" == "$localIndex" ]]; then
          found=true
          break
        fi
      done
      if [[ "$found" == false ]]; then
        echo "Deleting orphaned index: $cloudIndex"
        curl -X DELETE "https://${acs}/${stack}/adminconfig/v2/indexes/${cloudIndex}" \
          --header "Authorization: Bearer ${stack_jwt}" \
          --header "Content-Type: application/json"
        echo "Deleted index: $cloudIndex"
      fi
    done