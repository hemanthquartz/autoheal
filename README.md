name: Component Validation

on:
  pull_request:
    branches:
      - main

permissions:
  contents: read
  id-token: write

jobs:
  validate_components:
    runs-on: ubuntu-latest
    outputs:
      indexes-changed: ${{ steps.detect.outputs.indexes_changed }}
      hec-changed: ${{ steps.detect.outputs.hec_changed }}
      apps-changed: ${{ steps.detect.outputs.apps_changed }}
      ip-allowlist-changed: ${{ steps.detect.outputs.ip_allowlist_changed }}

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Detect Changed Files
        id: detect
        run: |
          git fetch origin main
          git diff --name-only origin/main...HEAD > changed_files.txt
          cat changed_files.txt

          indexes_changed=false
          hec_changed=false
          apps_changed=false
          ip_allowlist_changed=false

          while read file; do
            if [[ "$file" == src/indexes/* ]]; then
              indexes_changed=true
            elif [[ "$file" == src/hec/* ]]; then
              hec_changed=true
            elif [[ "$file" == src/apps/* ]]; then
              apps_changed=true
            elif [[ "$file" == src/ip-allow-list/* ]]; then
              ip_allowlist_changed=true
            fi
          done < changed_files.txt

          echo "indexes_changed=$indexes_changed" >> $GITHUB_OUTPUT
          echo "hec_changed=$hec_changed" >> $GITHUB_OUTPUT
          echo "apps_changed=$apps_changed" >> $GITHUB_OUTPUT
          echo "ip_allowlist_changed=$ip_allowlist_changed" >> $GITHUB_OUTPUT

  validate_indexes:
    needs: validate_components
    if: needs.validate_components.outputs.indexes-changed == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repo
        uses: actions/checkout@v4

      - name: Run Index Validation
        run: |
          echo "Running index validation..."
          # Add index validation logic here

  validate_hec:
    needs: validate_components
    if: needs.validate_components.outputs.hec-changed == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repo
        uses: actions/checkout@v4

      - name: Run HEC Validation
        run: |
          echo "Running HEC validation..."
          # Add HEC validation logic here

  validate_apps:
    needs: validate_components
    if: needs.validate_components.outputs.apps-changed == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repo
        uses: actions/checkout@v4

      - name: Run App Validation
        run: |
          echo "Running App validation..."
          # Add App validation logic here

  validate_ip_allowlist:
    needs: validate_components
    if: needs.validate_components.outputs.ip-allowlist-changed == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repo
        uses: actions/checkout@v4

      - name: Run IP Allowlist Validation
        run: |
          echo "Running IP allowlist validation..."
          # Add IP allowlist validation logic here