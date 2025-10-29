{
  "openapi": "3.0.3",
  "info": {
    "title": "splunk-to-azurefn-dispatch-np",
    "version": "1.0.0-np",
    "description": "Non-Prod API that receives Splunk webhooks and forwards them to an Azure Function (echo)."
  },
  "servers": [
    {
      "url": "https://api-np.<<<UPDATEME_ORG_DOMAIN>>>/observability/fn"
    }
  ],
  "security": [
    {
      "gateway": [
        "https://api.uhg.com/.default"
      ]
    }
  ],
  "x-domain": {
    "domain": "cloud",
    "subDomain": "applications"
  },
  "components": {
    "schemas": {
      "SplunkPayload": {
        "type": "object",
        "required": ["event_type", "client_payload"],
        "properties": {
          "event_type": { "type": "string", "example": "splunk_alert" },
          "client_payload": {
            "type": "object",
            "additionalProperties": true,
            "properties": {
              "action": { "type": "string", "example": "restart_service" },
              "env": { "type": "string", "example": "blue" },
              "vm_name": { "type": "string", "example": "obser-qa-blue" },
              "service_name": { "type": "string", "example": "ALG" }
            }
          }
        }
      },
      "Ok": { "type": "object", "properties": { "status": { "type": "string", "example": "ok" } } },
      "ErrorResponse": {
        "type": "object",
        "properties": { "message": { "type": "string" }, "status": { "type": "integer" } }
      }
    },
    "securitySchemes": {
      "gateway": {
        "type": "oauth2",
        "flows": {
          "clientCredentials": {
            "tokenUrl": "https://api.uhg.com/oauth2/token",
            "scopes": {
              "https://api.uhg.com/.default": "Default scope assigned to all clients"
            }
          }
        }
      }
    }
  },
  "paths": {
    "/splunk/dispatch": {
      "post": {
        "summary": "Receive Splunk webhook and forward to Azure Function (echo)",
        "operationId": "splunkDispatchToFn",
        "security": [ { "gateway": [ "https://api.uhg.com/.default" ] } ],
        "parameters": [
          {
            "name": "x-splunk-token",
            "in": "header",
            "required": true,
            "schema": { "type": "string", "minLength": 24 },
            "description": "Shared secret header. Rotated by platform automation."
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": { "schema": { "$ref": "#/components/schemas/SplunkPayload" } }
          }
        },
        "responses": {
          "200": { "description": "Function responded OK", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/Ok" } } } },
          "202": { "description": "Accepted by function" },
          "401": { "description": "Unauthorized", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/ErrorResponse" } } } },
          "429": { "description": "Too Many Requests" },
          "500": { "description": "Upstream error", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/ErrorResponse" } } } }
        },

        /* -------- HCP Gateway Runtime Extensions (adjust key names if your tenant differs) -------- */
        "x-gateway": {
          "route": {
            "protocol": "https",
            "timeoutMs": 10000
          },
          "backends": [
            {
              "name": "azfn",
              "host": "<<<UPDATEME_FUNCTION_APP_NAME>>>.azurewebsites.net",
              "port": 443,
              "protocol": "https",
              "location": "azure-eastus2"
            }
          ],
          "authz": {
            "header": "x-splunk-token",
            "source": "header",
            "mode": "required",
            "validation": {
              "type": "exact",
              "secretRef": "kv://<<<UPDATEME_KV_NAME>>>/splunk-fd-active-token"
            }
          },
          "request": {
            "backend": "azfn",
            "method": "POST",
            "path": "/api/echo",
            "headers": {
              "x-functions-key": "{{secret:`kv://<<<UPDATEME_KV_NAME>>>/azfn-echo-key-np`}}",
              "Content-Type": "application/json"
            },
            "bodyTemplate": {
              "engine": "passthrough"
            }
          },
          "responses": {
            "on2xx": { "passthrough": true },
            "on4xx": { "passthrough": true },
            "on5xx": { "passthrough": true }
          },
          "limits": {
            "rate": { "unit": "minute", "requests": 600 },
            "burst": 120
          }
        }
      }
    }
  },

  "instance": {
    "protocol": "https",
    "timeouts": { "read": 8000, "write": 8000, "connect": 2000 }
  },
  "environment": "nonprod",
  "serviceLevelObjectives": {
    "x-throughput": "10rps",
    "x-availability": "99.9",
    "x-responseTime": "1000",
    "x-maxMsgsPerDay": "10000"
  }
}