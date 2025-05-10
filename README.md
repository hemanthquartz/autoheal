jobs:
  ManageIndexes:
    runs-on: uhg-runner
    steps:
      # Existing steps
      - name: Perform Splunk list action
        run: |
          API_PATH="/adminconfig/v2/indexes"
          curl "https://${{ secrets.stack }}/${API_PATH}" --header "Authorization: Bearer ${{ secrets.stack_jwt }}" -o /tmp/currentIndexConfiguration.json

      - name: Upload Current Index Configuration
        if: ${{ success() }}
        uses: actions/upload-artifact@v4
        with:
          name: currentIndexConfiguration.json
          path: /tmp/currentIndexConfiguration.json
          retention-days: 5

      ####################################################
      # >>>>> NEW STEP: Parse JSON files with multiple indexes <<<<<
      ####################################################
      - name: Extract Index Names from Multi-Index JSON Files
        id: extract_indexes
        run: |
          echo "Extracting index definitions from multiple JSON files..."
          mkdir -p parsed_indexes
          for jsonFile in $(ls $GITHUB_WORKSPACE/indexes/*.json); do
            echo "Parsing file: $jsonFile"
            jq -c '.[]' "$jsonFile" | nl -nln > temp_index_list.txt
            while read -r line; do
              indexNum=$(echo "$line" | awk '{print $1}')
              indexDef=$(echo "$line" | cut -f2- -d' ')
              echo "$indexDef" > "parsed_indexes/index_${indexNum}_$(basename $jsonFile)"
            done < temp_index_list.txt
          done
          echo "Exported indexes:"
          ls parsed_indexes
        shell: bash

      ####################################################
      # >>>>> MODIFIED 'Create New Indexes' TO USE PARSED FILES <<<<<
      ####################################################
      - name: Create New Indexes
        if: ${{ inputs.select_action == 'add_indexes' }}
        run: |
          echo "Start: Creating new indexes"
          indexList=""
          echo "Fetching list of parsed index files..."
          for indexFile in $(ls parsed_indexes)
          do
            indexList="${indexList} ${indexFile}"
            echo "Found parsed index: ${indexFile}"
          done

          echo "Reading existing indexes from stack..."
          cloudList=$(jq -r '.[].name' /tmp/currentIndexConfiguration.json)
          echo "Fetched cloud index list"

          for indexFile in ${indexList}
          do
            index=$(jq -r '.name' parsed_indexes/${indexFile})
            echo "Checking if index ${index} exists in cloud..."
            if [[ $(echo "$cloudList" | jq -R -s -c 'split("\n")' | jq -r '.[]') != *"${index}"* ]]; then
              echo "[Creating Index]  ${index}"
              echo "Sending curl POST for ${index}"
              API_PATH="/adminconfig/v2/indexes"
              curl -X POST "https://${{ secrets.acs }}/${{ secrets.stack }}${API_PATH}" \
                --header "Authorization: Bearer ${{ secrets.stack_jwt }}" \
                --header "Content-Type: application/json" \
                --data @"parsed_indexes/${indexFile}"
              echo "POST complete"
              sleep 5
              echo "Checking creation status for ${index}"
              indexCreationStatus=$(curl -s "https://${{ secrets.acs }}/${{ secrets.stack }}/adminconfig/v2/indexes/${index}" \
                --header "Authorization: Bearer ${{ secrets.stack_jwt }}")
              echo "Received index creation status"
              echo "[Created Index] $(echo ${indexCreationStatus} | jq '.name')"
            else
              echo "[Index exists] Skipping ${index}"
            fi
          done