#!/usr/bin/env bash -e

echo "Starting index creation process..."
indexlist=$(ls $GETTING_WORKSPACE/indexes)
echo "Index list: $indexlist"

for indexFile in $(ls *.json); do
  echo "Reading file: $indexFile"
  indexlist="${indexlist} $(jq -r '.name' ${indexFile})"
done

echo "Combined Index List: $indexlist"
cloudList=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)
echo "Cloud Index List: $cloudList"

for index in ${indexlist}; do
  echo "Checking if $index exists in cloud..."
  if [[ $(echo "${cloudList}" | grep "^${index}$") ]]; then
    echo "$index already exists in cloud"
  else
    echo "Creating Index: $index"
    
    if [[ ! -f "${index}.json" ]]; then
      echo "ERROR: JSON file ${index}.json not found"
      exit 1
    fi

    echo "Sending curl request to create index..."
    curl -v -X POST "https://${stack}/adminconfig/v2/indexes" \
      --header "Authorization: ${token}" \
      --header 'Content-Type: application/json' \
      --data-raw "$(cat ${index}.json)" || { echo "Curl command failed for index ${index}"; exit 1; }

    sleep 3

    echo "Checking creation status..."
    indexCreationStatus=$(curl -s "https://${stack}/adminconfig/v2/indexes/${index}" \
      --header "Authorization: ${token}") || { echo "Failed to check creation status for ${index}"; exit 1; }

    echo "Raw creation status: $indexCreationStatus"
    LOOPCOUNTER=0

    while [[ $(echo ${indexCreationStatus} | jq -r '.code') == "404-index-not-found" ]]; do
      echo "Sleeping... [${LOOPCOUNTER} miss(es)]"
      sleep 15
      let LOOPCOUNTER=LOOPCOUNTER+1
      indexCreationStatus=$(curl -s "https://${stack}/adminconfig/v2/indexes/${index}" \
        --header "Authorization: ${token}") || { echo "Retry status check failed for ${index}"; exit 1; }
    done

    echo "[Created Index] => $(echo ${indexCreationStatus} | jq -r '.name')"
  fi
done