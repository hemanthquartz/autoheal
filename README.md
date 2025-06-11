- name: Send event to Splunk Observability
  if: always()
  run: |
    # Required metadata
    DEPLOYMENT_NAME="${{ github.workflow }}"
    REPO_NAME="${{ github.repository }}"
    ENVIRONMENT="${{ github.event.inputs.environment }}"
    COMPONENT="${{ github.event.inputs.select_component }}"
    STATUS="${{ job.status }}"
    START_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    DEPLOYMENT_ID="${{ github.run_id }}"
    VERSION_TAG="${{ github.ref_name }}"
    TRIGGERED_BY="${{ github.actor }}"

    # Construct event payload
    PAYLOAD=$(cat <<EOF
    {
      "eventType": "custom",
      "category": "deployment",
      "timestamp": "$(date +%s)000",
      "properties": {
        "aide_id": "${DEPLOYMENT_ID}",
        "repo": "${REPO_NAME}",
        "workflow": "${DEPLOYMENT_NAME}",
        "environment": "${ENVIRONMENT}",
        "component": "${COMPONENT}",
        "status": "${STATUS}",
        "start_time": "${START_TIME}",
        "triggered_by": "${TRIGGERED_BY}",
        "version": "${VERSION_TAG}"
      }
    }
EOF
    )

    # Send to Splunk Observability
    curl -X POST "https://api.${{ secrets.SPLUNK_REALM }}.signalfx.com/v2/event" \
         -H "Content-Type: application/json" \
         -H "X-SF-TOKEN: ${{ secrets.SPLUNK_SO_TOKEN }}" \
         -d "${PAYLOAD}"