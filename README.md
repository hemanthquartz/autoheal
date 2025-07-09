cd $GITHUB_WORKSPACE/new_indexes
pwd
ls -ltr

shopt -s nullglob
json_files=(*.json)
if [ ${#json_files[@]} -eq 0 ]; then
  echo "No new indexes to create. Exiting successfully."
  exit 0
fi

for jsonFile in "${json_files[@]}"; do
  echo "Creating index from: $jsonFile"
  curl -X POST "https://${acs}/${stack}/adminconfig/v2/indexes" \
    --header "Authorization: Bearer ${stack_jwt}" \
    --header "Content-Type: application/json" \
    --data @"$jsonFile"
done