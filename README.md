for file in parsed_indexes/*.json; do
  index_name=$(jq -r '.name' "$file")
  echo "Checking index: $index_name"

  # Get the remote definition for this index
  existing=$(jq -c --arg name "$index_name" '.[] | select(.name == $name)' /tmp/currentIndexConfiguration.json)

  if [[ -z "$existing" ]]; then
    echo "New index detected: $index_name"
    cp "$file" changed_indexes/
    continue
  fi

  # Compare only fields in local_def against remote_def
  change_found=0
  for key in $(jq -r 'keys[]' "$file"); do
    local_val=$(jq -r --arg k "$key" '.[$k]' "$file")
    remote_val=$(echo "$existing" | jq -r --arg k "$key" '.[$k] // "__MISSING__"')

    if [[ "$remote_val" != "$local_val" ]]; then
      echo "Attribute '$key' differs or missing: local='$local_val' vs remote='$remote_val'"
      change_found=1
    fi
  done

  if [[ "$change_found" == "1" ]]; then
    echo "Index $index_name has changed."
    cp "$file" changed_indexes/
  else
    echo "Index $index_name unchanged. Skipping."
  fi
done