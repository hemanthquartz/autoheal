      - name: Gather Changed Indexes
        id: gather_changed_indexes
        uses: tj-actions/changed-files@v35
        with:
          json: true
          quotepaths: false
          files: |
            parsed_indexes/*.json

      - name: Filter Out Unchanged Indexes
        if: ${{ steps.gather_changed_indexes.outputs.any_changed == 'true' }}
        run: |
          mkdir -p changed_indexes
          for file in $(echo '${{ steps.gather_changed_indexes.outputs.all_changed_files }}' | jq -r '.[]'); do
            cp "$file" changed_indexes/
          done

      - name: Override parsed_indexes with only changed ones
        if: ${{ steps.gather_changed_indexes.outputs.any_changed == 'true' }}
        run: |
          mv parsed_indexes parsed_indexes_all
          mv changed_indexes parsed_indexes