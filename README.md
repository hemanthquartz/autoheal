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
      stack: ${{ secrets.SPLUNK_STACK }}
      stack_jwt: ${{ secrets.SPLUNK_TOKEN }}
      acs: ${{ secrets.SPLUNK_URL }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Perform Splunk list action
        run: |
          echo "Action selected: ${{ github.event.inputs.action_type }}"

          # Prepare the URL based on the action
          if [ "${{ github.event.inputs.action_type }}" == "indexes" ]; then
            API_PATH="/adminconfig/v2/indexes"
          elif [ "${{ github.event.inputs.action_type }}" == "tokens" ]; then
            API_PATH="/adminconfig/v2/tokens"
          elif [ "${{ github.event.inputs.action_type }}" == "users" ]; then
            API_PATH="/adminconfig/v2/users"
          elif [ "${{ github.event.inputs.action_type }}" == "roles" ]; then
            API_PATH="/adminconfig/v2/roles"
          else
            echo "Invalid action type selected."
            exit 1
          fi

          curl -s "https://${acs}/${stack}${API_PATH}" \
            --header "Authorization: Bearer ${stack_jwt}" \
            --header "Content-Type: application/json" > splunk_list_output.json

          echo "Output saved to splunk_list_output.json"

      - name: Upload output as artifact
        uses: actions/upload-artifact@v4
        with:
          name: splunk-list-output
          path: splunk_list_output.json
          retention-days: 5
