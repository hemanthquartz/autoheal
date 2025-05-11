- name: Update Existing Indexes
  if: ${{ inputs.select_action == 'update_indexes' }}
  run: |
    echo "Start: Updating indexes from parsed files"
    cd parsed_indexes

    for file in $(ls); do
      echo "Processing file: ${file}"

      fileType=$(jq -r 'type' "$file")

      if [[ "$fileType" == "array" ]]; then
        total=$(jq length "$file")
        for ((i = 0; i < total; i++)); do
          localIndex=$(jq ".[$i]" "$file")
          process_index "$localIndex"
        done
      elif [[ "$fileType" == "object" ]]; then
        localIndex=$(cat "$file")
        process_index "$localIndex"
      else
        echo "Skipping file: $file — unsupported JSON type ($fileType)"
      fi
    done

    # Inline function to process and patch index
    process_index() {
      local localIndex="$1"
      indexName=$(echo "$localIndex" | jq -r '.name')
      echo "Checking index: $indexName"

      remoteIndex=$(jq --sort-keys '.[] | select(.name=="'"$indexName"'")' /tmp/currentIndexConfiguration.json)

      isSame=$(jq --argjson a "$localIndex" --argjson b "$remoteIndex" '$a == $b')
      if [[ "$isSame" == "true" ]]; then
        echo "[${indexName}] - No update required"
        return
      fi

      echo "[${indexName}] - Will be updated"
      jsonUpdate=$(echo '{}' | jq '.')

      for field in $(echo "$localIndex" | jq 'del(.name) | del(.datatype)' | jq -r 'keys[]'); do
        localVal=$(echo "$localIndex" | jq -r ".${field}")
        remoteVal=$(echo "$remoteIndex" | jq -r ".${field}")
        if [[ "$localVal" != "$remoteVal" ]]; then
          echo " - Field ${field}: ${remoteVal} -> ${localVal}"
          if [[ "$localVal" =~ ^[0-9]+$ ]]; then
            jsonUpdate=$(echo "$jsonUpdate" | jq --arg key "$field" --argjson val "$localVal" '. + {($key): $val}')
          else
            jsonUpdate=$(echo "$jsonUpdate" | jq --arg key "$field" --arg val "$localVal" '. + {($key): $val}')
          fi
        fi
      done

      echo "PATCH payload for $indexName: $jsonUpdate"

      curl -X PATCH "https://${{ secrets.acs }}/${{ secrets.stack }}/adminconfig/v2/indexes/${indexName}" \
        --header "Authorization: Bearer ${{ secrets.stack_jwt }}" \
        --header "Content-Type: application/json" \
        --data "$jsonUpdate"

      echo "Update complete for ${indexName}"
    }