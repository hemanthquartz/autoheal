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

    env:
      SPLUNK_URL: ${{ secrets.SPLUNK_URL }}
      SPLUNK_USERNAME: ${{ secrets.SPLUNK_USERNAME }}
      SPLUNK_PASSWORD: ${{ secrets.SPLUNK_PASSWORD }}

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Run Selected Splunk Cloud Action
        run: |
          set -e

          echo "Action selected: ${{ github.event.inputs.action }}"

          cd terraform/${{ github.event.inputs.action }}

          terraform init

          terraform plan \
            -var="splunk_url=$SPLUNK_URL" \
            -var="splunk_username=$SPLUNK_USERNAME" \
            -var="splunk_password=$SPLUNK_PASSWORD"

          terraform apply -auto-approve \
            -var="splunk_url=$SPLUNK_URL" \
            -var="splunk_username=$SPLUNK_USERNAME" \
            -var="splunk_password=$SPLUNK_PASSWORD"
