shopt -s nullglob
json_files=(*.json)
if [ ${#json_files[@]} -eq 0 ]; then
  echo "No changed indexes to update. Exiting successfully."
  exit 0
fi

for jsonFile in "${json_files[@]}"; do
  # ...your logic...
done