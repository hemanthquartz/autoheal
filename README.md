echo "Start: Creating new indexes"

indexlist=""
echo "Fetching list of index files..."
for indexFile in $(ls $GITHUB_WORKSPACE/indexes)
do
  indexlist="${indexlist} ${indexFile}"
  echo "Found index file: ${indexFile}"
done

echo "Reading existing indexes from stack..."
cloudList=$(curl -s -k -X GET "${stack}/adminconfig/v2/indexes" --header "Authorization: ***")
echo "Fetched cloud index list"

for index in ${indexlist}
do
  echo "Checking if index ${index} exists in cloud..."
  if [[ $(echo "${cloudList}" | jq -r '.[].name') != *"${index}"* ]]; then
    echo "[Creating Index] : ${index}"
    echo "Sending curl POST for ${index}"
    curl -X POST "https://${stack}/adminconfig/v2/indexes" \
      --header "Authorization: ***" \
      --header 'Content-Type: application/json' \
      --data-raw "$(cat ${index}.json)"
    echo "POST complete"

    sleep 5
    echo "Checking creation status for ${index}"
    indexCreationStatus=$(curl -s "https://${stack}/adminconfig/v2/indexes/${index}" --header "Authorization: ***")
    echo "Received index creation status"

    LOOPCOUNTER=0
    while [[ $(echo ${indexCreationStatus} | jq '.code' | sed 's/\"//g') == "non-index-not-found" ]]
    do
      echo "Sleeping... [${LOOPCOUNTER}] missed/up..."
      sleep 15
      let LOOPCOUNTER=LOOPCOUNTER+1
      echo "Retrying status check for ${index}"
      indexCreationStatus=$(curl -s "https://${stack}/adminconfig/v2/indexes/${index}" --header "Authorization: ***")
    done

    echo "[Created Index] : $(echo ${indexCreationStatus} | jq '.name')"
  else
    echo "[Index exists] Skipping ${index}"
  fi
done

echo "Done creating indexes"