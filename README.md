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
              "channel_adaptive_card": {
                "type": "object"
              },
              "approver_email": {
                "type": "string"
              },
              "callback_url": {
                "type": "string"
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
                "id": "card1",
                "contentType": "application/vnd.microsoft.card.adaptive",
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
                      "text": "@{coalesce(triggerBody()?['details'], 'Please review this approval request.')}",
                      "wrap": true
                    },
                    {
                      "type": "TextBlock",
                      "text": "Requested by: @{coalesce(triggerBody()?['requested_by'], 'Unknown')}",
                      "isSubtle": true,
                      "wrap": true
                    },
                    {
                      "type": "TextBlock",
                      "text": "Request ID: @{coalesce(triggerBody()?['request_id'], 'N/A')}",
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
                }
              }
            ]
          },
          "path": "/v3/beta/teams/@{encodeURIComponent('3cf5a8b2-aab5-4a45-ba98-f2a3781f8acf')}/channels/@{encodeURIComponent('19:7a3494c32a7f4a5cba9c64964a24579f@thread.tacv2')}/messages"
        },
        "runAfter": {}
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
          "decided_by": "@{coalesce(body('Parse_Teams_response')?['responder']?['userPrincipalName'], body('Parse_Teams_response')?['responder']?['displayName'], 'unknown')} via Teams",
          "outcome": "@if(equals(body('Parse_Teams_response')?['data']?['action'], 'approve'), 'Accepted', 'Rejected')",
          "request_id": "@coalesce(body('Parse_Teams_response')?['data']?['request_id'], triggerBody()?['request_id'])",
          "run_id": "@coalesce(body('Parse_Teams_response')?['data']?['run_id'], triggerBody()?['message_id'])",
          "source": "teams"
        },
        "runAfter": {
          "Parse_Teams_response": [
            "Succeeded"
          ]
        }
      },
      "POST_callback_to_MyCelium": {
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
            "request_id": "@outputs('Determine_approval')?['request_id']",
            "run_id": "@outputs('Determine_approval')?['run_id']",
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
            "status": "accepted",
            "request_id": "@triggerBody()?['request_id']",
            "approval_result": "@outputs('Determine_approval')"
          }
        },
        "runAfter": {
          "POST_callback_to_MyCelium": [
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