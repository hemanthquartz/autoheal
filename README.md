# Splunk OpenTelemetry Collector - agent_config.yaml (Windows)
# Adds Windows Service status -> SignalFx (Splunk Observability)
#
# Required environment variables (set by installer or your system):
#   SPLUNK_ACCESS_TOKEN  : Splunk Observability access token
#   SPLUNK_API_URL       : e.g., https://api.us0.signalfx.com
#   SPLUNK_INGEST_URL    : e.g., https://ingest.us0.signalfx.com
#   SPLUNK_HEC_TOKEN     : (optional) Splunk HEC token (if using HEC exporters)
#   SPLUNK_HEC_URL       : (optional) Splunk HEC URL, e.g., https://http-inputs-<realm>.splunkcloud.com/services/collector
#   SPLUNK_BUNDLE_DIR    : Smart Agent bundle dir (usually set by installer)
#   SPLUNK_COLLECTD_DIR  : collectd config dir (usually set by installer)
#   SPLUNK_LISTEN_INTERFACE: Interface/IP to listen on (default 0.0.0.0)
#   SPLUNK_MEMORY_LIMIT_MIB: e.g., 512
#   SPLUNK_GATEWAY_URL   : (optional) If forwarding to a gateway collector
#
# Notes:
# - This file is tailored from the default config, with the `windows_service` receiver enabled
#   and a dedicated metrics pipeline `metrics/windows_services` that exports to SignalFx.
# - Safe to use on a single-collector "agent" install on Windows.
# - Keep indentation (spaces) intact.

extensions:
  headers_setter:
    actions:
      - action: upsert
        key: X-SF-Token
        from_context: X-SF-Token
        default:
          value: "${SPLUNK_ACCESS_TOKEN}"
  health_check:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:13133"
  http_forwarder:
    ingress:
      endpoint: "${SPLUNK_LISTEN_INTERFACE}:6060"
    egress:
      endpoint: "${SPLUNK_API_URL}"
  zpages:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:55679"
  smartagent:
    bundleDir: "${SPLUNK_BUNDLE_DIR}"
    collectd:
      configDir: "${SPLUNK_COLLECTD_DIR}"

receivers:
  fluentforward:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:8006"

  hostmetrics:
    collection_interval: 10s
    scrapers:
      cpu: {}
      disk: {}
      filesystem: {}
      memory: {}
      network: {}
      processes: {}

  jaeger:
    protocols:
      grpc:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:14250"
      thrift_binary:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:6832"
      thrift_compact:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:6831"
      thrift_http:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:14268"

  otlp:
    protocols:
      grpc:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4317"
        include_metadata: true
      http:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4318"
        include_metadata: true

  prometheus/internal:
    config:
      scrape_configs:
        - job_name: "otel-collector"
          scrape_interval: 10s
          static_configs:
            - targets: ["0.0.0.0:8888"]
          metric_relabel_configs:
            - source_labels: [__name__]
              regex: "promhttp_metric_handler_errors.*"
              action: drop
            - source_labels: [__name__]
              regex: "otelcol_processor_batch_.*"
              action: drop

  smartagent/processlist:
    type: processlist
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:9411"

  zipkin:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:9411"

  # ✅ NEW: Collect all Windows service states
  windows_service:
    collection_interval: 60s
    include:
      - ".*"   # regex to include all services

processors:
  batch: {}

  memory_limiter:
    check_interval: 2s
    limit_mib: ${SPLUNK_MEMORY_LIMIT_MIB}

  resourcedetection:
    detectors: [ec2, azure, system]
    override: true

  resource/add_environment:
    attributes:
      - action: insert
        key: deployment.environment
        value: production

  resource/add_mode:
    attributes:
      - action: insert
        key: otelcol.service.mode
        value: agent

exporters:
  otlphttp:
    traces_endpoint: "${SPLUNK_INGEST_URL}/v2/trace/otlp"
    headers:
      "X-SF-Token": "${SPLUNK_ACCESS_TOKEN}"
    auth:
      authenticator: headers_setter

  signalfx:
    access_token: "${SPLUNK_ACCESS_TOKEN}"
    api_url: "${SPLUNK_API_URL}"
    ingest_url: "${SPLUNK_INGEST_URL}"
    sync_host_metadata: true

  splunk_hec:
    token: "${SPLUNK_HEC_TOKEN}"
    endpoint: "${SPLUNK_HEC_URL}"
    source: "otel"
    sourcetype: "otel"
    profiling_data_enabled: false
    log_data_enabled: true

  splunk_hec/profiling:
    token: "${SPLUNK_HEC_TOKEN}"
    endpoint: "${SPLUNK_INGEST_URL}/v1/log"
    profiling_data_enabled: false

  otlp/gateway:
    endpoint: "${SPLUNK_GATEWAY_URL}:4317"
    tls:
      insecure: true
    auth:
      authenticator: headers_setter

service:
  extensions: [headers_setter, health_check, http_forwarder, zpages, smartagent]

  pipelines:
    traces:
      receivers: [jaeger, otlp, zipkin]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [otlphttp, signalfx]

    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter, batch, resourcedetection, resource/add_environment, resource/add_mode]
      exporters: [signalfx]

    metrics/internal:
      receivers: [prometheus/internal]
      processors: [memory_limiter, batch, resourcedetection, resource/add_mode]
      exporters: [signalfx]

    # ✅ NEW: Windows Services status metrics -> SignalFx
    metrics/windows_services:
      receivers: [windows_service]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]

    logs:
      receivers: [fluentforward, otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [splunk_hec]

    logs/entities:
      receivers: [fluentforward, otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [splunk_hec]