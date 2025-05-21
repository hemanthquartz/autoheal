      - name: Override parsed_indexes with only changed ones
        if: ${{ steps.gather_changed_indexes.outputs.any_changed == 'true' }}
        run: |
          if [ "$(ls -A changed_indexes)" ]; then
            mv parsed_indexes parsed_indexes_all
            mv changed_indexes parsed_indexes
          else
            echo "No changed index files found. Keeping full parsed_indexes."
          fi