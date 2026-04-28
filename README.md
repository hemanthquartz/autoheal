{
  "definition": {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "contentVersion": "1.0.0.0",
    "triggers": {
      "When_a_HTTP_request_is_received": {
        "type": "Request",
        "kind": "Http",
        "inputs": {
          "method": "POST",
          "schema": {
            "type": "object",
            "properties": {
              "title": { "type": "string" },
              "details": { "type": "string" },
              "request_id": { "type": "string" },
              "message_id": { "type": "string" },
              "requested_by": { "type": "string" },
              "approver_email": { "type": "string" },
              "callback_url": { "type": "string" },
              "adaptive_card": { "type": "object" },
              "channel_adaptive_card": { "type": "object" },
              "message_card": { "type": "object" }
            }
          }
        }
      }
    },
    "actions": {
      "Post_channel_card": {
        "type": "ApiConnection",
        "inputs": {
          "host": {
            "connection": {
              "name": "@parameters('$connections')['teams']['connectionId']"
            }
          },
          "method": "post",
          "body": {
            "body": {
              "content": "<attachment id=\"card1\"></attachment>",
              "contentType": "html"
            },
            "attachments": [
              {
                "content": "@json(string(coalesce(triggerBody()?['channel_adaptive_card'], triggerBody()?['message_card'])))",
                "contentType": "application/vnd.microsoft.card.adaptive",
                "id": "card1"
              }
            ]
          },
          "path": "/v3/beta/teams/@{encodeURIComponent(parameters('teamId'))}/channels/@{encodeURIComponent(parameters('channelId'))}/messages"
        },
        "runAfter": {}
      },
      "Response_with_message_id": {
        "type": "Response",
        "kind": "Http",
        "inputs": {
          "statusCode": 200,
          "headers": {
            "Content-Type": "application/json"
          },
          "body": {
            "message_id": "@body('Post_channel_card')?['id']",
            "request_id": "@triggerBody()?['request_id']",
            "status": "accepted"
          }
        },
        "runAfter": {
          "Post_channel_card": [
            "Succeeded"
          ]
        }
      },
      "Post_dm_card_and_wait": {
        "type": "ApiConnectionWebhook",
        "inputs": {
          "host": {
            "connection": {
              "name": "@parameters('$connections')['teams']['connectionId']"
            }
          },
          "body": {
            "recipient": "@triggerBody()?['approver_email']",
            "messageBody": "@json(string(triggerBody()?['adaptive_card']))",
            "notificationUrl": "@listCallbackUrl()"
          },
          "path": "/v1.0/teams/conversation/adaptivecard/waitforresponse"
        },
        "runAfter": {
          "Response_with_message_id": [
            "Succeeded"
          ]
        }
      },
      "Parse_Teams_response": {
        "type": "ParseJson",
        "inputs": {
          "content": "@body('Post_dm_card_and_wait')",
          "schema": {
            "type": "object",
            "properties": {
              "data": {
                "type": "object",
                "properties": {
                  "action": {
                    "type": "string"
                  },
                  "request_id": {
                    "type": "string"
                  },
                  "run_id": {
                    "type": "string"
                  }
                }
              },
              "responder": {
                "type": "object",
                "properties": {
                  "displayName": {
                    "type": "string"
                  },
                  "userPrincipalName": {
                    "type": "string"
                  }
                }
              },
              "submitActionId": {
                "type": "string"
              }
            }
          }
        },
        "runAfter": {
          "Post_dm_card_and_wait": [
            "Succeeded"
          ]
        }
      },
      "Determine_approval": {
        "type": "Compose",
        "inputs": {
          "approved": "@equals(body('Parse_Teams_response')?['data']?['action'], 'approve')",
          "decided_by": "@coalesce(body('Parse_Teams_response')?['responder']?['userPrincipalName'], body('Parse_Teams_response')?['responder']?['displayName'], 'via Teams')",
          "outcome": "@if(equals(body('Parse_Teams_response')?['data']?['action'], 'approve'), 'Accepted', 'Rejected')"
        },
        "runAfter": {
          "Parse_Teams_response": [
            "Succeeded"
          ]
        }
      },
      "POST_callback_to_Mycelium": {
        "type": "Http",
        "inputs": {
          "uri": "@coalesce(triggerBody()?['callback_url'], parameters('defaultCallbackUrl'))",
          "method": "POST",
          "headers": {
            "Content-Type": "application/json"
          },
          "body": {
            "approved": "@outputs('Determine_approval')?['approved']",
            "decided_by": "@outputs('Determine_approval')?['decided_by']",
            "outcome": "@outputs('Determine_approval')?['outcome']",
            "request_id": "@coalesce(body('Parse_Teams_response')?['data']?['request_id'], triggerBody()?['request_id'])",
            "run_id": "@body('Parse_Teams_response')?['data']?['run_id']",
            "message_id": "@body('Post_channel_card')?['id']",
            "source": "teams"
          }
        },
        "runAfter": {
          "Determine_approval": [
            "Succeeded"
          ]
        }
      }
    },
    "outputs": {},
    "parameters": {
      "teamId": {
        "type": "String",
        "defaultValue": "3cf5a8b2-aab5-4a45-ba98-f2a3781f8acf"
      },
      "channelId": {
        "type": "String",
        "defaultValue": "19:7a3494c32a7f4a5cba9c64964a24579f@thread.tacv2"
      },
      "defaultCallbackUrl": {
        "type": "String",
        "defaultValue": "https://pde-automation-hub-backend-eastus-np-pr-120.azurewebsites.net/api/v1/workflow/approval-callback"
      },
      "$connections": {
        "type": "Object",
        "defaultValue": {}
      }
    }
  },
  "parameters": {
    "$connections": {
      "value": {
        "teams": {
          "id": "/subscriptions/5204df69-30ab-4345-a9d2-ddb0ac139a3c/providers/Microsoft.Web/locations/eastus/managedApis/teams",
          "connectionId": "/subscriptions/5204df69-30ab-4345-a9d2-ddb0ac139a3c/resourceGroups/pde-automation-hub-eastus-rg-qa/providers/Microsoft.Web/connections/teams",
          "connectionName": "teams",
          "connectionProperties": {}
        }
      }
    }
  }
}