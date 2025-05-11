- name: Update Existing Indexes
  if: ${{ inputs.select_action == 'update_indexes' }}
  run: |
    echo "Start: Updating indexes"
    indexList=""
    cd parsed_indexes
    echo "Creating a list of parsed index files..."
    for indexFile in $(ls)
    do
      indexList="${indexList} $(jq -r '.name' ${indexFile})"
    done

    for index in ${indexList}
    do
      echo "[${index}] - Evaluating..."

      indexFile=$(ls | grep -i "${index}" | head -n1)  # <<< ADDED
      localIndex=$(jq --sort-keys . ${indexFile})      # <<< FIXED

      remoteIndex=$(jq --sort-keys '.[] | select(.name=="'${index}'")' /tmp/currentIndexConfiguration.json)

      if [[ "$(jq --argjson a "${localIndex}" --argjson b "${remoteIndex}" '$a == $b' <<< '{}')" == "true" ]]; then
        echo "[${index}] - No Update Required"
        continue
      fi

      echo "[${index}] - Local and Remote do not match, updating remote to reflect git"
      jsonUpdate="{"
      for indexVar in $(echo ${localIndex} | jq 'del(.name) | del(.datatype)' | jq -r 'keys[]'); do
        localIndexVar=$(echo ${localIndex} | jq -r ".${indexVar}")
        remoteIndexVar=$(echo ${remoteIndex} | jq -r ".${indexVar}")
        if [[ "$localIndexVar" != "$remoteIndexVar" ]]; then
          echo "[${index}] - ${indexVar}: ${remoteIndexVar} -> ${localIndexVar}"
          jsonUpdate="${jsonUpdate}\"${indexVar}\":\"${localIndexVar}\","
        fi
      done
      jsonUpdate="${jsonUpdate%?}}" # Remove trailing comma and close JSON

      echo "Sending PATCH to update ${index}"
      curl -X PATCH "https://${{ secrets.acs }}/${{ secrets.stack }}/adminconfig/v2/indexes/${index}" \
        --header "Authorization: Bearer ${{ secrets.stack_jwt }}" \
        --header "Content-Type: application/json" \
        --data "${jsonUpdate}"
      echo "Update complete for ${index}"
    done