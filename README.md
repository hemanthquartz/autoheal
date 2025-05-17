- name: Install Python dependencies
  run: |
    python3 -m pip install --upgrade pip
    pip install jsonschema

- name: Validate JSON Against OpenAPI Schema using Python
  run: |
    python3 <<EOF
    import json
    import sys
    from jsonschema import validate, Draft7Validator, ValidationError

    with open("${{ matrix.index }}", "r") as f:
        data = json.load(f)

    with open("/tmp/openapi.json", "r") as f:
        schema = json.load(f)

    # If this is a list of objects (as expected for indexes.json)
    if isinstance(data, list):
        for idx, item in enumerate(data):
            try:
                validate(instance=item, schema=schema)
            except ValidationError as e:
                print(f"[ERROR] Validation failed for item #{idx + 1} in file: ${{ matrix.index }}")
                print(e.message)
                sys.exit(1)
    else:
        try:
            validate(instance=data, schema=schema)
        except ValidationError as e:
            print(f"[ERROR] Validation failed for file: ${{ matrix.index }}")
            print(e.message)
            sys.exit(1)
    print("[SUCCESS] Validation passed for ${{ matrix.index }}")
    EOF
