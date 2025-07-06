- name: Perform Splunk Cloud index list action with pagination
  run: |
    API_PATH="/adminconfig/v2/indexes"
    OFFSET=0
    STRIDE=100
    MAX_INDEXES=${{ env.splunk_cloud_max_index }}
    STACK="${stack}"
    ACS="${acs}"
    TOKEN="${stack_jwt}"
    OUTFILE="/tmp/currentIndexConfiguration.json"
    echo "[]" > "$OUTFILE"

    while [ $OFFSET -lt $MAX_INDEXES ]; do
      echo "Fetching indexes with offset=$OFFSET"
      RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        "https://${ACS}/${STACK}${API_PATH}?offset=${OFFSET}&count=${STRIDE}")

      COUNT=$(echo "$RESPONSE" | jq 'length')

      if [ "$COUNT" -eq 0 ]; then
        echo "No more indexes to fetch. Exiting."
        break
      fi

      # Merge current response into cumulative file
      jq -s '.[0] + .[1]' "$OUTFILE" <(echo "$RESPONSE") > /tmp/tmp_indexes.json
      mv /tmp/tmp_indexes.json "$OUTFILE"

      OFFSET=$((OFFSET + STRIDE))
    done

    echo "Indexes fetched and saved to $OUTFILE"