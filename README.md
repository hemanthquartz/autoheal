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
      name:
        description: "Name of Index, Role, HEC, or App"
        required: false
        default: ""
      description:
        description: "Optional description for HEC/App/Role"
        required: false
        default: ""

jobs:
  run_splunk_action:
    runs-on: ubuntu-latest

    env:
      SPLUNK_URL: ${{ secrets.SPLUNK_URL }}
      SPLUNK_USERNAME: ${{ secrets.SPLUNK_USERNAME }}
      SPLUNK_PASSWORD: ${{ secrets.SPLUNK_PASSWORD }}
      NAME: ${{ github.event.inputs.name }}
      DESCRIPTION: ${{ github.event.inputs.description }}

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Run Splunk Cloud Action
        run: |
          set -e

          echo "Action selected: ${{ github.event.inputs.action }}"
          echo "Name provided: $NAME"
          echo "Description provided: $DESCRIPTION"

          # Navigate into the right Terraform module
          cd terraform/${{ github.event.inputs.action }}

          # Initialize Terraform
          terraform init

          # Terraform Plan (Dry Run)
          terraform plan \
            -var="splunk_url=$SPLUNK_URL" \
            -var="splunk_username=$SPLUNK_USERNAME" \
            -var="splunk_password=$SPLUNK_PASSWORD" \
            -var="name=$NAME" \
            -var="description=$DESCRIPTION"

          # Terraform Apply
          terraform apply -auto-approve \
            -var="splunk_url=$SPLUNK_URL" \
            -var="splunk_username=$SPLUNK_USERNAME" \
            -var="splunk_password=$SPLUNK_PASSWORD" \
            -var="name=$NAME" \
            -var="description=$DESCRIPTION"
