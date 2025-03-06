
jobs:
  JarBuild:
    name: Code Build and Upload
    runs-on: uhg-runner
    steps:
      - name: Clean Workspace Before Checkout
        run: |
          echo "Deleting all files in the workspace..."
          rm -rf ./*
          echo "Workspace cleaned."

      - name: Code Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 20
        uses: actions/setup-java@v3
        with:
          java-version: 20
          distribution: "temurin"
          overwrite-settings: false

      - name: Set up Maven
        uses: stCarolas/setup-maven@v4.5
        with:
          maven-version: 3.8.8

      - name: Ensure Required Directories Exist
        run: mkdir -p target scripts/lib

      - name: Build and Package with Maven
        run: mvn clean package -DskipTests=false

      - name: Move JAR to Target Directory
        run: |
          JAR_FILE=$(find ./ -name "otel-demo-*.jar" | grep -v "./target/")
          echo "Moving $JAR_FILE to ./target/"
          mv "$JAR_FILE" ./target/

      - name: Grant Execute Permission to Scripts
        run: chmod +x scripts/*.sh

      - name: Upload All Required Files to Azure Storage
        run: |
          az storage blob upload-batch \
            --account-name 'artifacts887d4b66' \
            --destination 'otel-installation' \
            --source 'target/' \
            --source 'scripts/' \
            --auth-mode key \
            --account-key 'DyeJ3JMH4nvLk0yRR13mSeSZViPDqOg+mxj1lNX16oqgZDlXfP1B9UQHoGTCJ@wk5dxoD2KrcGnflRq91JPeXb5w=' \
            --overwrite


jobs:
  JarBuild:
    name: Code Build
    runs-on: uhg-runner
    steps:
      - name: Code Checkout
        uses: actions/checkout@v4

      - name: Set up JDK 20
        uses: actions/setup-java@v3
        with:
          java-version: 20
          distribution: "temurin"
          overwrite-settings: false

      - name: Set up Maven
        uses: stCarolas/setup-maven@v4.5
        with:
          maven-version: 3.8.8

      - name: Build and Package with Maven
        run: mvn clean package -DskipTests=false

      - name: Ensure Target Directory Exists
        run: mkdir -p scripts/lib target otel-setup

      - name: Copy Required Files for OpenTelemetry Installation
        run: |
          # Copy the JAR file to the target directory
          JAR_FILE=$(find ./ -name "otel-demo-*.jar" | grep -v "./target/")
          if [ -n "$JAR_FILE" ] && [ "$JAR_FILE" != "./target/$(basename $JAR_FILE)" ]; then
            echo "Copying $JAR_FILE to ./target/"
            cp "$JAR_FILE" ./target/
          else
            echo "JAR file is already in target directory, skipping copy."
          fi

          # Copy OpenTelemetry setup scripts
          cp scripts/startup.sh otel-setup/
          cp scripts/install-otel.sh otel-setup/
          cp scripts/config.yaml otel-setup/  # Example configuration file

      - name: Grant Execute Permission to Scripts
        run: chmod +x scripts/startup.sh scripts/install-otel.sh

      - name: Upload OpenTelemetry Setup Files to Azure Storage
        run: |
          az storage blob upload-batch \
            --account-name 'artifacts887d4b66' \
            --destination 'otel-installation' \
            --source 'otel-setup/' \
            --auth-mode key \
            --account-key 'DyeJ3JMH4nvLk0yRR13mSeSZViPDqOg+mxj1lNX16oqgZDlXfP1B9UQHoGTCJ@wk5dxoD2KrcGnflRq91JPeXb5w=' \
            --overwrite


index=* 
| rex field=_raw "(?i)(?<message>.*?)(?:\s(?:stream_name|start process|session id|transaction id|user id|because|for|due to|reason|error code)\b.*)?$"
| stats count by message
| sort -count
| head 20


index=* 
| rex field=_raw "(?i)^(?<message>[^,]+(?:\s[^,]+)?)"
| stats count, earliest(_time) AS first_seen, latest(_time) AS last_seen by message
| eval first_seen=strftime(first_seen, "%Y-%m-%d %H:%M:%S"), last_seen=strftime(last_seen, "%Y-%m-%d %H:%M:%S")
| sort -count
| head 20


name: Verify JAR with OpenTelemetry on VM

on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

jobs:
  otel-verification:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v3
        with:
          distribution: 'temurin'
          java-version: '17'

      - name: Install Maven
        run: |
          sudo apt update
          sudo apt install -y maven
          mvn -version

      - name: Build JAR with OpenTelemetry
        run: mvn clean package -DskipTests=false

      - name: Run JAR with OpenTelemetry
        run: |
          export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
          export OTEL_SERVICE_NAME="otel-demo"
          export OTEL_TRACES_EXPORTER="otlp"
          export OTEL_METRICS_EXPORTER="otlp"
          export OTEL_LOGS_EXPORTER="otlp"

          nohup java -jar target/otel-demo-0.0.1-SNAPSHOT.jar --server.port=9090 > app.log 2>&1 &
          sleep 10
          cat app.log

      - name: Verify OpenTelemetry Logs
        run: grep "otel.instrumentation" app.log || echo "No OpenTelemetry logs found"

      - name: Stop and Uninstall JAR
        run: |
          pkill -f "otel-demo-0.0.1-SNAPSHOT.jar" || echo "No process found"
          rm -f app.log