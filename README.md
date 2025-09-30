- name: Install Tools
  run: |
    sudo apt-get update && sudo apt-get install -y unzip jq curl file
    sudo wget https://github.com/mikefarah/yq/releases/download/v4.44.2/yq_linux_amd64 -O /usr/bin/yq
    sudo chmod +x /usr/bin/yq

- name: Extract askId
  id: extract_askid
  run: |
    ASK_ID=$(yq -r '.metadata.askId | (if type=="array" then .[0] else . end)' vitals.yaml)
    echo "askid=${ASK_ID}" >> "$GITHUB_OUTPUT"
    echo "Extracted askId: ${ASK_ID}"