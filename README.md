- name: Update Existing Indexes
  if: ${{ inputs.select_action == 'update_indexes' }}
  run: |
    echo "Start: Updating indexes from multi-index files"
    cd parsed_indexes

    for file in $(ls); do
      echo "Processing file: ${file}"
      updatesToSend="{}"

      count=$(jq length "${file}")
      for ((i=0; i<$count; i++)); do
        localIndex=$(jq ".[$i]" "${file}")
        indexName=$(echo "${localIndex}" | jq -r '.name')
        echo "Checking index: ${indexName}"

        remoteIndex=$(jq --sort-keys '.[] | select(.name=="'${indexName}'")' /tmp/currentIndexConfiguration.json)

        # Compare full object
        if [[ "$(jq --argjson a "${localIndex}" --argjson b "${remoteIndex}" '$a == $b' <<< '{}')" == "true" ]]; then
          echo "[${indexName}] - No update required"
          continue
        fi

        echo "[${indexName}] - Will be updated"
        indexPatch="{}"

        for field in $(echo "${localIndex}" | jq 'del(.name) | del(.datatype)' | jq -r 'keys[]'); do
          localVal=$(echo "${localIndex}" | jq -r ".${field}")
          remoteVal=$(echo "${remoteIndex}" | jq -r ".${field}")

          if [[ "$localVal" != "$remoteVal" ]]; then
            echo " - Field ${field}: ${remoteVal} -> ${localVal}"
            if [[ "$localVal" =~ ^[0-9]+$ ]]; then
              indexPatch=$(echo "$indexPatch" | jq --arg key "$field" --argjson val "$localVal" '. + {($key): $val}')
            else
              indexPatch=$(echo "$indexPatch" | jq --arg key "$field" --arg val "$localVal" '. + {($key): $val}')
            fi
          fi
        done

        # Add this index's update to the overall JSON payload
        updatesToSend=$(echo "$updatesToSend" | jq --arg key "$indexName" --argjson val "$indexPatch" '. + {($key): $val}')
      done

      echo "Final PATCH payload for file ${file}: $updatesToSend"

      if [[ "$updatesToSend" != "{}" ]]; then
        curl -X PATCH "https://${{ secrets.acs }}/${{ secrets.stack }}/adminconfig/v2/indexes" \
          --header "Authorization: Bearer ${{ secrets.stack_jwt }}" \
          --header "Content-Type: application/json" \
          --data "$updatesToSend"
        echo "PATCH completed for file: ${file}"
      else
        echo "No changes needed from ${file}"
      fi
    done