#!/bin/bash
set -euo pipefail

echo "Listing Splunk Indexes using ACS API..."

if [[ -z "${SPLUNK_STACK:-}" ]]; then
  echo "ERROR: SPLUNK_STACK not defined."
  exit 1
fi

if [[ -z "${SPLUNK_TOKEN:-}" ]]; then
  echo "ERROR: SPLUNK_TOKEN (Bearer token) not defined."
  exit 1
fi

for i in {1..3}; do
  response=$(curl -s -H "Authorization: Bearer ${SPLUNK_TOKEN}" \
    "https://admin.splunk.com/${SPLUNK_STACK}/adminconfig/v2/indexes" || true)

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