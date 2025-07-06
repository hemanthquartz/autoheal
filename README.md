- name: Perform Splunk list action
  run: |
    API_PATH="/adminconfig/v2/indexes"
    AUTH_HEADER="Authorization: Bearer ${stack_jwt}"
    OUT_FILE="/tmp/currentIndexConfiguration.json"
    BASE_URL="https://${acs}/${stack}${API_PATH}"

    echo "Fetching all indexes from Splunk Cloud with pagination..."
    > "$OUT_FILE"

    NEXT_URL="$BASE_URL"

    while [[ -n "$NEXT_URL" ]]; do
      echo "Requesting: $NEXT_URL"
      RESPONSE=$(curl -s -H "$AUTH_HEADER" "$NEXT_URL")

      # Append all embedded indexes to file
      INDEXES=$(echo "$RESPONSE" | jq -c '._embedded.indexes[]?')
      if [[ -z "$INDEXES" ]]; then
        echo "No indexes found in response or invalid response format."
        break
      fi

      echo "$INDEXES" >> "$OUT_FILE"

      # Detect next link
      NEXT_PATH=$(echo "$RESPONSE" | jq -r '._links.next.href // empty')
      if [[ -n "$NEXT_PATH" ]]; then
        NEXT_URL="https://${acs}/${stack}$NEXT_PATH"
      else
        NEXT_URL=""
      fi
    done

    echo "Final merged index list:"
    jq -s '.' "$OUT_FILE" > "${OUT_FILE}.tmp" && mv "${OUT_FILE}.tmp" "$OUT_FILE"
    cat "$OUT_FILE" | jq '.'