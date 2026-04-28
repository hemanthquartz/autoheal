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
              "action": {
                "type": "string"
              },
              "adaptive_card": {
                "type": "object"
              },
              "approver_email": {
                "type": "string"
              },
              "callback_url": {
                "type": "string"
              },
              "channel_adaptive_card": {
                "type": "object"
              },
              "details": {
                "type": "string"
              },
              "message_card": {
                "type": "object"
              },
              "message_id": {
                "type": "string"
              },
              "request_id": {
                "type": "string"
              },
              "requested_by": {
                "type": "string"
              },
              "title": {
                "type": "string"
              }
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
                "content": "@json(string(coalesce(triggerBody()?['channel_adaptive_card'], triggerBody()?['adaptive_card'])))",
                "contentType": "application/vnd.microsoft.card.adaptive",
                "id": "card1"
              }
            ]
          },
          "path": "/v3/beta/teams/@{encodeURIComponent('3cf5a8b2-aab5-4a45-ba98-f2a3781f8acf')}/channels/@{encodeURIComponent('19:7a3494c32a7f4a5cba9c64964a24579f@thread.tacv2')}/messages"
        },
        "runAfter": {}
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
            "notificationUrl": "@listCallbackUrl()",
            "body": {
              "content": "<attachment id=\"card1\"></attachment>",
              "contentType": "html"
            },
            "attachments": [
              {
                "content": {
                  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                  "type": "AdaptiveCard",
                  "version": "1.4",
                  "body": [
                    {
                      "type": "TextBlock",
                      "text": "@{coalesce(triggerBody()?['title'], 'Approval Request')}",
                      "weight": "Bolder",
                      "size": "Medium",
                      "wrap": true
                    },
                    {
                      "type": "TextBlock",
                      "text": "@{coalesce(triggerBody()?['details'], 'Please review and respond.')}",
                      "wrap": true
                    },
                    {
                      "type": "TextBlock",
                      "text": "Requested by: @{coalesce(triggerBody()?['requested_by'], 'unknown')}",
                      "isSubtle": true,
                      "wrap": true
                    }
                  ],
                  "actions": [
                    {
                      "type": "Action.Submit",
                      "title": "Approve",
                      "data": {
                        "action": "approve",
                        "request_id": "@{triggerBody()?['request_id']}",
                        "run_id": "@{triggerBody()?['message_id']}"
                      }
                    },
                    {
                      "type": "Action.Submit",
                      "title": "Reject",
                      "data": {
                        "action": "reject",
                        "request_id": "@{triggerBody()?['request_id']}",
                        "run_id": "@{triggerBody()?['message_id']}"
                      }
                    }
                  ]
                },
                "contentType": "application/vnd.microsoft.card.adaptive",
                "id": "card1"
              }
            ]
          },
          "path": "/v3/beta/teams/@{encodeURIComponent('3cf5a8b2-aab5-4a45-ba98-f2a3781f8acf')}/channels/@{encodeURIComponent('19:7a3494c32a7f4a5cba9c64964a24579f@thread.tacv2')}/messages"
        },
        "runAfter": {
          "Post_channel_card": [
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
          "decided_by": "@{body('Parse_Teams_response')?['responder']?['userPrincipalName']} via Teams",
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
          "uri": "@coalesce(triggerBody()?['callback_url'], 'https://pde-automation-hub-backend-eastus-np-pr-120.azurewebsites.net/api/v1/workflow/approval-callback')",
          "method": "POST",
          "headers": {
            "Content-Type": "application/json"
          },
          "body": {
            "approved": "@outputs('Determine_approval')?['approved']",
            "decided_by": "@outputs('Determine_approval')?['decided_by']",
            "outcome": "@outputs('Determine_approval')?['outcome']",
            "request_id": "@coalesce(body('Parse_Teams_response')?['data']?['request_id'], triggerBody()?['request_id'])",
            "source": "teams"
          }
        },
        "runAfter": {
          "Determine_approval": [
            "Succeeded"
          ]
        }
      },
      "Response_with_message_id": {
        "type": "Response",
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
          "POST_callback_to_Mycelium": [
            "Succeeded"
          ]
        }
      }
    },
    "parameters": {
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
          "connectionId": "/subscriptions/5204df69-30ab-4345-a9d2-ddb0ac139a3c/resourceGroups/pde-automation-hub-eastus-np-rg/providers/Microsoft.Web/connections/teams",
          "connectionName": "teams"
        }
      }
    }
  }
}