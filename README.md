- name: Install Node.js and ajv-cli
  run: |
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
    npm install -g ajv-cli

- name: Validate JSON Using AJV CLI
  run: |
    ajv validate -s /tmp/openapi.json -d ${{ matrix.index }} --strict=false
