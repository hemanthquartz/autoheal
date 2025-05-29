echo "Start: Creating new indexes"
indexlist=""

# Build a list of all index names from parsed index files
for file in parsed_indexes/*; do
  index=$(jq -r '.name' "$file")
  echo "Found index: $index from file: $file"
  indexlist="$indexlist $index"
done

echo "Reading existing indexes from stack..."
cloudList=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)
echo "Fetched cloud index list"

# Now safely iterate over actual index names
for index in $indexlist; do
  echo "Checking if index $index exists in cloud..."
  if [[ $(echo "$cloudList" | jq -r --arg name "$index" '. | index($name)') == "null" ]]; then
    echo "[Creating Index] : $index"
    echo "Sending curl POST for $index"

    curl -X POST "https://${acs}/${stack}/adminconfig/v2/indexes" \
      --header "Authorization: Bearer ${stack_jwt}" \
      --header "Content-Type: application/json" \
      --data "@parsed_indexes/${index}.json"

    echo "POST complete"
    sleep 5
  else
    echo "[Index exists] skipping $index"
  fi
done