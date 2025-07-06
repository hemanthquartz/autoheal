- name: Compare extracted indexes with Splunk Cloud and filter only new/changed
  run: |
    mkdir -p changed_indexes

    for file in parsed_indexes/*.json; do
      index_name=$(jq -r '.name' "$file")
      echo "Checking index: $index_name"

      existing=$(jq -c --arg name "$index_name" '.[] | select(.name == $name)' /tmp/currentIndexConfiguration.json)

      if [[ -z "$existing" ]]; then
        echo "New index detected: $index_name"
        cp "$file" changed_indexes/
        continue
      fi

      local_def=$(jq -S 'del(.datatype)' "$file")
      remote_def=$(echo "$existing" | jq -S 'del(.datatype)')

      if [[ "$local_def" != "$remote_def" ]]; then
        echo "Index $index_name has changed."
        cp "$file" changed_indexes/
      else
        echo "Index $index_name unchanged. Skipping."
      fi
    done