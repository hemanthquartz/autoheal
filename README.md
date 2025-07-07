- name: List all Splunk Cloud indexes (auto-pagination)
  run: |
    API_PATH="/adminconfig/v2/indexes"
    BASE_URL="https://${acs}/${stack}${API_PATH}"
    TOKEN="${stack_jwt}"
    STRIDE=100

    rm -f /tmp/indexes_*.json

    offset=0
    while true; do
      echo "Fetching indexes with offset $offset"
      RESPONSE_FILE="/tmp/indexes_${offset}.json"

      curl -sSL "${BASE_URL}?offset=${offset}&count=${STRIDE}" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -o "$RESPONSE_FILE"

      # Stop if response is empty or just null
      if ! jq -e . "$RESPONSE_FILE" > /dev/null || grep -q null "$RESPONSE_FILE"; then
        echo "No more data at offset $offset. Stopping."
        rm -f "$RESPONSE_FILE"
        break
      fi

      offset=$((offset + STRIDE))
    done

    # Merge valid JSON
    jq -s '[.[][]]' /tmp/indexes_*.json > /tmp/all_indexes.json || echo "No index data"
    cat /tmp/all_indexes.json || echo "Merged file is empty"
  env:
    acs: ${{ secrets.acs }}
    stack: ${{ secrets.stack }}
    stack_jwt: ${{ secrets.stack_jwt }}