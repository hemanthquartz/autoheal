      - name: Filter Parsed Indexes Against Splunk Cloud Config
        run: |
          mkdir -p filtered_indexes

          for file in parsed_indexes/*.json; do
            index_name=$(jq -r '.name' "$file")
            remote_index=$(jq -c --arg name "$index_name" '.[] | select(.name == $name)' /tmp/currentIndexConfiguration.json)

            if [[ -z "$remote_index" ]]; then
              echo "[New] $index_name -> adding for create"
              cp "$file" filtered_indexes/
            else
              is_same=$(jq --argjson a "$remote_index" --argjson b "$(cat "$file")" '$a == $b' <<< '{}')
              if [[ "$is_same" != "true" ]]; then
                echo "[Updated] $index_name -> adding for update"
                cp "$file" filtered_indexes/
              else
                echo "[Unchanged] $index_name -> skipping"
              fi
            fi
          done

      - name: Replace parsed_indexes with filtered indexes
        run: |
          mv parsed_indexes parsed_indexes_all
          mv filtered_indexes parsed_indexes
