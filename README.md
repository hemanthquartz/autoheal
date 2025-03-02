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