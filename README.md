- name: Validate JSON Against Schema
  uses: ebiwd/json-schema-validator@v1
  with:
    schema: /tmp/openapi.json
    json: ${{ matrix.index }}



- name: Install ajv-cli
  run: npm install -g ajv-cli

- name: Validate Index JSON
  run: |
    ajv validate -s /tmp/openapi.json -d ${{ matrix.index }} --strict=false
