# Default configuration file for the Linux (deb/rpm) and Windows MSI collector packages

# If the collector is installed without the Linux/Windows installer script, the following
# environment variables are required to be manually defined or configured below:
# - SPLUNK_ACCESS_TOKEN: The Splunk access token to authenticate requests
# - SPLUNK_API_URL: The Splunk API URL, e.g. https://api.us0.signalfx.com
# - SPLUNK_BUNDLE_DIR: The path to the Smart Agent bundle, e.g. /usr/lib/splunk-otel-collector/agent-bundle
# - SPLUNK_COLLECTD_DIR: The path to the collected config directory for the Smart Agent, e.g. /usr/lib/splunk-otel-collector/agent-bundle/run/collectd
# - SPLUNK_HEC_TOKEN: The Splunk HEC authentication token
# - SPLUNK_HEC_URL: The Splunk HEC endpoint URL, e.g. https://http-inputs-acme.splunkcloud.com
# - SPLUNK_INGEST_URL: The Splunk ingest URL, e.g. https://ingest.us0.signalfx.com
# - SPLUNK_LISTEN_INTERFACE: The network interface the agent receivers listen on.

extensions:
  headers_setter:
    headers:
      - action: upsert
        key: X-SF-TOKEN
        from_context: X-SF-TOKEN
        value: "${SPLUNK_ACCESS_TOKEN}"
  health_check:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:13133"
  http_forwarder:
    ingress:
      endpoint: "${SPLUNK_LISTEN_INTERFACE}:6060"
  smartagent:
    bundleDir: "${SPLUNK_BUNDLE_DIR}"
    collectd:
      configDir: "${SPLUNK_COLLECTD_DIR}"
  zpages:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:55679"
    enabled: true

receivers:
  fluentforward:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:8006"
  hostmetrics:
    collection_interval: 10s
    scrapers:
      cpu:
      disk:
      filesystem:
      load:
      memory:
      paging:
      processes:
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
      http:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4318"
  prometheus/internal:
    config:
      scrape_configs:
        - job_name: 'otel-collector'
          scrape_interval: 10s
          static_configs:
            - targets: ["0.0.0.0:8888"]
      metric_relabel_configs:
        - source_labels: [ __name__ ]
          regex: 'promhttp_metric_handler_errors.*'
          action: drop
        - source_labels: [ __name__ ]
          regex: 'otelcol_processor_batch.*'
          action: drop
  smartagent/processlist:
    type: processlist
  smartagent/windows_services:
    type: windows_services
    interval: 60s
  zipkin:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:9411"

processors:
  batch:
  metadata/keys:
    keys:
      - X-SF-TOKEN
  memory_limiter:
    check_interval: 2s
    limit_mib: ${SPLUNK_MEMORY_LIMIT_MIB}
  resourcedetection:
    detectors: [ec2, ecs, azure, system]
  resource/add_environment:
    attributes:
      - action: insert
        value: staging/production/...
        key: deployment.environment
  resource/add_mode:
    attributes:
      - action: insert
        value: agent
        key: otelcol.service.mode

exporters:
  otlphttp:
    traces_endpoint: "${SPLUNK_INGEST_URL}/v2/trace/otlp"
    headers:
      "X-SF-TOKEN": "${SPLUNK_ACCESS_TOKEN}"
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
    log_data_enabled: false

  splunk_hec/profiling:
    token: "${SPLUNK_ACCESS_TOKEN}"
    endpoint: "${SPLUNK_INGEST_URL}/v1/log"

  otlp/gateway:
    endpoint: "${SPLUNK_GATEWAY_URL}:4317"
    tls:
      insecure: true
    auth:
      authenticator: headers_setter

debug:
  verbosity: detailed

service:
  extensions: [headers_setter, health_check, http_forwarder, zpages, smartagent]
  pipelines:
    traces:
      receivers: [jaeger, otlp, zipkin]
      processors: [memory_limiter, batch, resourcedetection, resource/add_environment]
      exporters: [otlphttp, signalfx]
    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]
    metrics/internal:
      receivers: [prometheus/internal]
      processors: [memory_limiter, batch, resourcedetection, resource/add_mode]
      exporters: [signalfx]
    logs/signalfx:
      receivers: [smartagent/processlist, smartagent/windows_services]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]
    logs/entities:
      receivers: [nop]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [otlphttp/entities]
    logs:
      receivers: [fluentforward, otlp]
      processors:
        - memory_limiter
        - batch
        - resourcedetection
        - resource/add_environment
      exporters: [splunk_hec, splunk_hec/profiling]