# Default configuration file for the Linux (deb/rpm) and Windows MSI collector packages

# If the collector is installed without the Linux/Windows installer script, the following
# environment variables are required to be manually defined or configured below:
# - SPLUNK_ACCESS_TOKEN: The Splunk access token to authenticate requests
# - SPLUNK_API_URL: The Splunk API URL, e.g. https://api.us0.signalfx.com
# - SPLUNK_BUNDLE_DIR: The path to the Smart Agent bundle, e.g. /usr/lib/splunk-otel-collector/agent-bundle
# - SPLUNK_COLLECTD_DIR: The path to the collected config directory for the Smart Agent, e.g. /usr/lib/splunk-otel-collector/agent-bundle/run/collectd
# - SPLUNK_HEC_TOKEN: The Splunk HEC authentication token
# - SPLUNK_HEC_URL: The Splunk HEC endpoint URL, e.g. https://http-inputs-acme.splunkcloud.com/services/collector
# - SPLUNK_INGEST_URL: The Splunk ingest URL, e.g. https://ingest.us0.signalfx.com
# - SPLUNK_LISTEN_INTERFACE: The network interface the agent receivers listen on.

extensions:
  headers_setter:
    processors:
      - action: upsert
        key: X-SF-TOKEN
        from_context: X-SF-TOKEN
        value: "${SPLUNK_ACCESS_TOKEN}"
  health_check:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:13133"
  http_forwarder:
    ingress:
      endpoint: "${SPLUNK_LISTEN_INTERFACE}:6060"
    egress:
      endpoint: "${SPLUNK_API_URL}"
  smartagent:
    bundleDir: "${SPLUNK_BUNDLE_DIR}"
    collectd:
      configDir: "${SPLUNK_COLLECTD_DIR}"
  zpages:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:55679"

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
      network:
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
        include_metadata: true
      http:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4318"
        include_metadata: true
  prometheus/internal:
    config:
      scrape_configs:
        - job_name: 'otel-collector'
          scrape_interval: 10s
          static_configs:
            - targets: ["0.0.0.0:8888"]
      metric_relabel_configs:
        - source_labels: [ __name__ ]
          regex: "promhttp_metric_handler_errors.*"
          action: drop
        - source_labels: [ __name__ ]
          regex: "otelcol_processor_batch.*"
          action: drop
  smartagent/processlist:
    type: processlist
  zipkin:
    endpoint: "${SPLUNK_LISTEN_INTERFACE}:9411"

  # Added receiver to collect Windows service status
  smartagent/win_services:
    type: windows-service
    intervalSeconds: 60
    sendAll: true

processors:
  batch:
  memory_limiter:
    check_interval: 2s
    limit_mib: ${SPLUNK_MEMORY_LIMIT_MIB}
  resourcedetection:
    detectors: [env, ec2, ecs, azure, system]
    override: true
  resource/add_environment:
    attributes:
      - action: insert
        key: deployment.environment
        value: staging
  resource/add_mode:
    attributes:
      - action: insert
        key: otelcol.service.mode
        value: agent

exporters:
  # Traces
  otlphttp:
    traces_endpoint: "${SPLUNK_INGEST_URL}/v2/trace/otlp"
    headers:
      "X-SF-TOKEN": "${SPLUNK_ACCESS_TOKEN}"
    auth:
      authenticator: headers_setter

  # Metrics + Events
  signalfx:
    access_token: "${SPLUNK_ACCESS_TOKEN}"
    api_url: "${SPLUNK_API_URL}"
    ingest_url: "${SPLUNK_INGEST_URL}"
    # Use instead when sending to gateway
    # ingest_url: http://${SPLUNK_GATEWAY_URL}:6060
    # ingest_url: http://${SPLUNK_GATEWAY_URL}:9943
    sync_host_metadata: true

  # Logs
  splunk_hec:
    token: "${SPLUNK_HEC_TOKEN}"
    endpoint: "${SPLUNK_HEC_URL}"
    source: "otel"
    sourcetype: "otel"
    profiling_data_enabled: false

  # Profiling
  splunk_hec/profiling:
    token: "${SPLUNK_ACCESS_TOKEN}"
    endpoint: "${SPLUNK_INGEST_URL}/v1/log"
    log_data_enabled: false

  # Send to gateway
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
      # exporters: [otlp/gateway, signalfx]

    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]
      # exporters: [otlp/gateway]

    metrics/internal:
      receivers: [prometheus/internal]
      processors: [memory_limiter, batch, resourcedetection, resource/add_mode]
      exporters: [signalfx]

    # Added pipeline to send Windows service metrics
    metrics/windows_services:
      receivers: [smartagent/win_services]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]

    logs/signalfx:
      receivers: [smartagent/processlist]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [signalfx]

    logs/entities:
      receivers: [nop]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: [otlphttp/entities]
      # exporters: [otlp/gateway]

    logs:
      receivers: [fluentforward, otlp]
      processors:
        - memory_limiter
        - batch
        - resourcedetection
        - resource/add_environment
      exporters: [splunk_hec, splunk_hec/profiling]
      # exporters: [otlp/gateway]