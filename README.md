echo "Start: Updating indexes"
cd $GITHUB_WORKSPACE/parsed_indexes
pwd
ls -ltr

for jsonFile in *.json; do
  echo "Processing file: ${jsonFile}"

  # Read index name from file
  index=$(jq -r '.name' "$jsonFile")
  localIndex=$(jq '.' "$jsonFile")
  echo "[${index}] - Evaluating..."

  # Extract matching remote index
  remoteIndex=$(jq --sort-keys --arg index "$index" '.[] | select(.name == $index)' /tmp/currentIndexConfiguration.json)

  # Skip if local and remote are identical
  if [[ "$(jq -n --argjson a "$localIndex" --argjson b "$remoteIndex" '$a == $b')" == "true" ]]; then
    echo "[${index}] - No Update Required"
    continue
  fi

  echo "[${index}] - Local and Remote do not match, updating remote to reflect git"

  jsonUpdate=$(echo '{}' | jq '.')

  for key in $(echo "$localIndex" | jq 'del(.name, .datatype) | keys[]' -r); do
    localVal=$(echo "$localIndex" | jq -r --arg k "$key" '.[$k]')
    remoteVal=$(echo "$remoteIndex" | jq -r --arg k "$key" '.[$k] // "__MISSING__"')

    if [[ "$localVal" != "$remoteVal" ]]; then
      echo "  → Field changed: $key: $remoteVal → $localVal"
      jsonUpdate=$(echo "$jsonUpdate" | jq --arg key "$key" --arg val "$localVal" '. + {($key): $val}')
    fi
  done

  echo "PATCH payload for ${index}: $jsonUpdate"

  curl -X PATCH "https://${acs}/${stack}/adminconfig/v2/indexes/${index}" \
    --header "Authorization: Bearer ${stack_jwt}" \
    --header "Content-Type: application/json" \
    --data "$jsonUpdate"

  echo "Update complete for ${index}"
done