jsonUpdate=$(echo '{}' | jq '.')
for indexVar in $(echo "${localIndex}" | jq 'del(.name) | del(.datatype)' | jq -r 'keys[]'); do
  localIndexVar=$(echo "${localIndex}" | jq -r ".${indexVar}")
  remoteIndexVar=$(echo "${remoteIndex}" | jq -r ".${indexVar}")
  if [[ "$localIndexVar" != "$remoteIndexVar" ]]; then
    echo "[${index}] - ${indexVar}: ${remoteIndexVar} -> ${localIndexVar}"
    jsonUpdate=$(echo "${jsonUpdate}" | jq --arg key "$indexVar" --arg val "$localIndexVar" '. + {($key): $val}')
  fi
done