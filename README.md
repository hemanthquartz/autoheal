- name: List all Splunk Cloud indexes (paginated)
  run: |
    API_PATH="/adminconfig/v2/indexes"
    BASE_URL="https://${acs}/${stack}${API_PATH}"
    TOKEN="${stack_jwt}"
    MAX_INDEX=500  # Customize this based on your expected max count
    STRIDE=100

    rm -f /tmp/indexes_*.json

    for (( offset=0; offset<=MAX_INDEX; offset+=STRIDE )); do
      echo "Fetching indexes with offset $offset"
      curl -sSL "${BASE_URL}?offset=${offset}&count=${STRIDE}" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -o /tmp/indexes_${offset}.json
    done

    # Merge all JSON responses into one file
    jq -s '[.[][]]' /tmp/indexes_*.json > /tmp/all_indexes.json
  env:
    acs: ${{ secrets.acs }}
    stack: ${{ secrets.stack }}
    stack_jwt: ${{ secrets.stack_jwt }}