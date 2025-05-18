- name: Validate Index Not starting with underscore
  run: |
    for file in parsed_indexes/*.json; do
      name=$(jq -r '.name' "$file")
      if [[ "$name" =~ ^_ ]]; then
        echo "[Error] Index '$name' in $file should not start with _"
        exit 1
      fi
    done



- name: Validate Index Name Characters
  run: |
    for file in parsed_indexes/*.json; do
      name=$(jq -r '.name' "$file")
      if [[ ! "$name" =~ ^[A-Za-z0-9_.-]+$ ]]; then
        echo "[Error] Index '$name' in $file contains invalid characters"
        exit 1
      fi
    done