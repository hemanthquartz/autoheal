echo "Start: Creating new indexes"

echo "Fetching list of index files..."
for indexFile in $(ls new_indexes); do
  indexList=$(jq -r '.[].name' "new_indexes/${indexFile}")
  echo "Found index file: ${indexFile}"
  
  for index in ${indexList}; do
    echo "Creating index: ${index}"
    
    API_PATH="adminconfig/v2/indexes"
    
    curl -X POST "https://${acs}/${stack}/${API_PATH}" \
      --header "Authorization: Bearer ${stack_jwt}" \
      --header "Content-Type: application/json" \
      --data "@new_indexes/${indexFile}"
    
    sleep 5
    
    # Optionally wait until index is created successfully
    indexCreationStatus=$(curl -s "https://${acs}/${stack}/adminconfig/v2/indexes/${index}" \
      --header "Authorization: Bearer ${stack_jwt}")
    
    LOOPCOUNTER=0
    while [[ $(echo "$indexCreationStatus" | jq -r '.code // empty') == "non-index-not-found" ]]; do
      echo "Sleeping... [$LOOPCOUNTER] index creation not complete for ${index}"
      sleep 15
      let LOOPCOUNTER=LOOPCOUNTER+1
      indexCreationStatus=$(curl -s "https://${acs}/${stack}/adminconfig/v2/indexes/${index}" \
        --header "Authorization: Bearer ${stack_jwt}")
    done
    
    echo "[Created Index] $index => $(echo "$indexCreationStatus" | jq -r '.name')"
  done
done