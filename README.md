name: List Splunk Cloud Components

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Splunk Environment (dev, qa, prod)'
        required: true
        default: 'dev'
        type: choice
        options:
          - dev
          - qa
          - prod
      action_type:
        description: 'Action to perform (indexes, tokens, users, roles)'
        required: true
        default: 'indexes'
        type: choice
        options:
          - indexes
          - tokens
          - users
          - roles

jobs:
  list_components:
    runs-on: ubuntu-latest
    env:
      SPLUNK_PASSWORD: ${{ secrets.SPLUNK_PASSWORD }}
      SPLUNK_STACK: ${{ secrets.SPLUNK_STACK }}
      SPLUNK_TOKEN: ${{ secrets.SPLUNK_TOKEN }}
      SPLUNK_URL: ${{ secrets.SPLUNK_URL }}
      SPLUNK_USERNAME: ${{ secrets.SPLUNK_USERNAME }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set environment variables based on selected environment
        run: |
          echo "Selected environment: ${{ github.event.inputs.environment }}"
          if [ "${{ github.event.inputs.environment }}" == "dev" ]; then
            echo "SPLUNK_URL=${{ secrets.SPLUNK_URL }}" >> $GITHUB_ENV
          elif [ "${{ github.event.inputs.environment }}" == "qa" ]; then
            echo "SPLUNK_URL=${{ secrets.SPLUNK_URL }}" >> $GITHUB_ENV
          elif [ "${{ github.event.inputs.environment }}" == "prod" ]; then
            echo "SPLUNK_URL=${{ secrets.SPLUNK_URL }}" >> $GITHUB_ENV
          else
            echo "Invalid environment selected."
            exit 1
          fi

      - name: Perform Splunk list action
        run: |
          echo "Action selected: ${{ github.event.inputs.action_type }}"

          # Prepare the URL based on the action
          if [ "${{ github.event.inputs.action_type }}" == "indexes" ]; then
            API_PATH="/services/data/indexes?count=0&output_mode=json"
          elif [ "${{ github.event.inputs.action_type }}" == "tokens" ]; then
            API_PATH="/services/authorization/tokens?count=0&output_mode=json"
          elif [ "${{ github.event.inputs.action_type }}" == "users" ]; then
            API_PATH="/services/authentication/users?count=0&output_mode=json"
          elif [ "${{ github.event.inputs.action_type }}" == "roles" ]; then
            API_PATH="/services/authorization/roles?count=0&output_mode=json"
          else
            echo "Invalid action type selected."
            exit 1
          fi

          FULL_URL="https://${{ env.SPLUNK_STACK }}.${{ env.SPLUNK_URL }}${API_PATH}"

          echo "Calling URL: $FULL_URL"

          curl -k -sS --request GET "$FULL_URL" \
            --header "Authorization: Bearer ${{ env.SPLUNK_TOKEN }}" \
            --header "Content-Type: application/json" > splunk_list_output.json

          echo "Output saved to splunk_list_output.json"

      - name: Upload output as artifact
        uses: actions/upload-artifact@v4
        with:
          name: splunk-list-output
          path: splunk_list_output.json
