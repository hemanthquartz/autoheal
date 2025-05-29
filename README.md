response=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "https://${acs}/${stack}/adminconfig/v2/indexes/${index}" \
  --header "Authorization: Bearer ${stack_jwt}" \
  --header "Content-Type: application/json" \
  --data "$jsonUpdate")

if [[ "$response" -eq 400 ]]; then
  echo "Skipped updating $index: invalid payload."
  continue
fi

echo "Update complete for ${index}"



response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "https://${acs}/${stack}/adminconfig/v2/indexes" \
  --header "Authorization: Bearer ${stack_jwt}" \
  --header "Content-Type: application/json" \
  --data "@parsed_indexes/${index}.json")

if [[ "$response" -eq 400 ]]; then
  echo "Skipped creating $index: invalid payload."
  continue
fi

echo "Created index: $index"