name: Splunk Cloud Manager

on:
  workflow_dispatch:
    inputs:
      action:
        description: "Select an action to perform"
        required: true
        type: choice
        options:
          - list_indexes
          - add_index
          - add_role_mapping
          - add_hec
          - create_app

jobs:
  run_splunk_action:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Initialize Terraform Provider
        run: |
          cd terraform/common
          terraform init

      - name: Execute Selected Action
        run: |
          chmod +x scripts/run_action.sh
          ./scripts/run_action.sh ${{ github.event.inputs.action }}
