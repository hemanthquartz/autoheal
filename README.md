      - name: Compare extracted indexes with Splunk Cloud and filter only new/changed
        run: |
          mkdir -p changed_indexes
          for file in parsed_indexes/*.json; do
            index_name=$(jq -r '.name' "$file")
            # Check if index exists in cloud
            existing=$(jq -c --arg name "$index_name" '.[] | select(.name == $name)' /tmp/currentIndexConfiguration.json)
            if [[ -z "$existing" ]]; then
              echo "New index detected: $index_name"
              cp "$file" changed_indexes/
            else
              local_def=$(jq -cS . "$file")
              remote_def=$(echo "$existing" | jq -cS .)
              if [[ "$local_def" != "$remote_def" ]]; then
                echo "Index $index_name changed"
                cp "$file" changed_indexes/
              else
                echo "Index $index_name unchanged. Skipping."
              fi
            fi
          done

      - name: Override parsed_indexes with only new/updated ones
        run: |
          if [ "$(ls -A changed_indexes)" ]; then
            rm -rf parsed_indexes
            mv changed_indexes parsed_indexes
          else
            echo "No new or changed indexes detected. All further steps will be skipped."
            mkdir -p parsed_indexes  # To prevent loop errors if dir doesn't exist
          fi