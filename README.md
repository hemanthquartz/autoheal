{
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
            "requested_by": { "type": "string" },
            "approver_email": { "type": "string" }
          }
        }
      }
    }
  },
  "actions": {
    "Post_adaptive_card_and_wait": {
      "type": "ApiConnectionWebhook",
      "inputs": {
        "host": {
          "connection": {
            "name": "@parameters('$connections')['teams']['connectionId']"
          }
        },
        "body": {
          "message": {
            "body": {
              "contentType": "html",
              "content": "<attachment id=\"card1\"></attachment>"
            }
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
                    "text": "@{triggerBody()?['title']}",
                    "weight": "Bolder",
                    "size": "Medium"
                  },
                  {
                    "type": "TextBlock",
                    "text": "@{triggerBody()?['details']}",
                    "wrap": true
                  },
                  {
                    "type": "TextBlock",
                    "text": "Requested by: @{triggerBody()?['requested_by']}",
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
                      "request_id": "@{triggerBody()?['request_id']}"
                    }
                  },
                  {
                    "type": "Action.Submit",
                    "title": "Reject",
                    "data": {
                      "action": "reject",
                      "request_id": "@{triggerBody()?['request_id']}"
                    }
                  }
                ]
              }
            }
          ]
        },
        "path": "/v1.0/teams/@{encodeURIComponent(parameters('teamId'))}/channels/@{encodeURIComponent(parameters('channelId'))}/messages"
      }
    },

    "Parse_Teams_response": {
      "type": "ParseJson",
      "runAfter": {
        "Post_adaptive_card_and_wait": ["Succeeded"]
      },
      "inputs": {
        "content": "@body('Post_adaptive_card_and_wait')",
        "schema": {
          "type": "object",
          "properties": {
            "data": {
              "type": "object",
              "properties": {
                "action": { "type": "string" },
                "request_id": { "type": "string" }
              }
            },
            "responder": {
              "type": "object",
              "properties": {
                "userPrincipalName": { "type": "string" },
                "displayName": { "type": "string" }
              }
            }
          }
        }
      }
    },

    "Determine_approval": {
      "type": "Compose",
      "runAfter": {
        "Parse_Teams_response": ["Succeeded"]
      },
      "inputs": {
        "approved": "@equals(body('Parse_Teams_response')?['data']?['action'], 'approve')",
        "decided_by": "@body('Parse_Teams_response')?['responder']?['userPrincipalName']",
        "outcome": "@if(equals(body('Parse_Teams_response')?['data']?['action'], 'approve'), 'Accepted', 'Rejected')"
      }
    },

    "POST_callback_to_backend": {
      "type": "Http",
      "runAfter": {
        "Determine_approval": ["Succeeded"]
      },
      "inputs": {
        "method": "POST",
        "uri": "https://your-backend/api/approval",
        "headers": {
          "Content-Type": "application/json"
        },
        "body": {
          "approved": "@outputs('Determine_approval')?['approved']",
          "decided_by": "@outputs('Determine_approval')?['decided_by']",
          "outcome": "@outputs('Determine_approval')?['outcome']",
          "request_id": "@body('Parse_Teams_response')?['data']?['request_id']",
          "source": "teams"
        }
      }
    },

    "Response": {
      "type": "Response",
      "runAfter": {
        "POST_callback_to_backend": ["Succeeded"]
      },
      "inputs": {
        "statusCode": 200,
        "body": {
          "status": "Approval processed"
        }
      }
    }
  },

  "parameters": {
    "teamId": {
      "type": "string",
      "defaultValue": "<TEAM_ID>"
    },
    "channelId": {
      "type": "string",
      "defaultValue": "<CHANNEL_ID>"
    },
    "$connections": {
      "type": "Object"
    }
  }
}