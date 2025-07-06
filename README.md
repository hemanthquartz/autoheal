- name: Perform Splunk list action
  run: |
    API_PATH="/adminconfig/v2/indexes"
    AUTH_HEADER="Authorization: Bearer ${stack_jwt}"
    BASE_URL="https://${acs}/${stack}${API_PATH}"
    OUT_FILE="/tmp/currentIndexConfiguration.json"

    echo "Fetching all indexes with pagination..."
    > "$OUT_FILE"  # Clear file

    NEXT_URL="$BASE_URL"
    while [[ -n "$NEXT_URL" ]]; do
      echo "Requesting: $NEXT_URL"

      RESPONSE=$(curl -s -H "$AUTH_HEADER" "$NEXT_URL")
      echo "$RESPONSE" | jq '.[]' >> "$OUT_FILE"

      # Detect nextLink or use offset pagination
      NEXT_LINK=$(echo "$RESPONSE" | jq -r '._links.next.href // empty')
      if [[ -n "$NEXT_LINK" ]]; then
        NEXT_URL="https://${acs}/${stack}$NEXT_LINK"
      else
        NEXT_URL=""
      fi
    done

    echo "Final fetched index config:"
    cat "$OUT_FILE" | jq '.'