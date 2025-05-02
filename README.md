name: SplunkCloud List Fetch

on:
  workflow_dispatch:
    inputs:
      list_action:
        description: "Select what to list"
        required: true
        type: choice
        options:
          - list_indexes
          - list_tokens
          - list_users
          - list_roles

jobs:
  fetch_list:
    runs-on: ubuntu-latest
    env:
      SPLUNK_URL: ${{ secrets.SPLUNK_URL }}
      SPLUNK_USERNAME: ${{ secrets.SPLUNK_USERNAME }}
      SPLUNK_PASSWORD: ${{ secrets.SPLUNK_PASSWORD }}
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Install jq
        run: sudo apt-get install jq -y

      - name: Fetch Selected List
        run: |
          chmod +x scripts/${{ github.event.inputs.list_action }}.sh
          ./scripts/${{ github.event.inputs.list_action }}.sh




name: SplunkCloud Manage Actions

on:
  workflow_dispatch:
    inputs:
      action:
        description: "Select Create Action"
        required: true
        type: choice
        options:
          - add_index
          - add_hec
          - add_role
          - create_app

jobs:
  run_manage_action:
    runs-on: ubuntu-latest
    environment: production
    env:
      SPLUNK_URL: ${{ secrets.SPLUNK_URL }}
      SPLUNK_USERNAME: ${{ secrets.SPLUNK_USERNAME }}
      SPLUNK_PASSWORD: ${{ secrets.SPLUNK_PASSWORD }}

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Initialize Terraform
        run: |
          cd terraform/common
          terraform init

      - name: Prepare Terraform Plan
        run: |
          cd terraform/${{ github.event.inputs.action }}
          terraform init
          terraform plan -out=tfplan \
            -var="splunk_url=$SPLUNK_URL" \
            -var="splunk_username=$SPLUNK_USERNAME" \
            -var="splunk_password=$SPLUNK_PASSWORD"
          terraform show tfplan

      - name: Wait for Manual Approval
        uses: chrnorm/deployment-approval@v2
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          environment: production

      - name: Apply after Approval
        run: |
          cd terraform/${{ github.event.inputs.action }}
          terraform apply tfplan



#!/bin/bash
set -euo pipefail

echo "Listing Splunk Indexes..."

for i in {1..3}; do
  response=$(curl -s -u "$SPLUNK_USERNAME:$SPLUNK_PASSWORD" \
    "https://${SPLUNK_URL}:8089/services/data/indexes?output_mode=json" -k || true)

  if echo "$response" | jq . >/dev/null 2>&1; then
    echo "$response" | jq .
    exit 0
  else
    echo "Attempt $i: Failed to retrieve indexes. Retrying..."
    sleep 2
  fi
done

echo "ERROR: Could not retrieve indexes after multiple attempts."
exit 1




