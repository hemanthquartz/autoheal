{
  "type": "If",
  "expression": {
    "and": [
      {
        "equals": [
          "@outputs('Start_and_wait_for_an_approval')?['body/outcome']",
          "Approve"
        ]
      }
    ]
  },
  "actions": {
    "Compose": {
      "type": "Compose",
      "inputs": "Accepted"
    },
    "Response": {
      "type": "Response",
      "kind": "Http",
      "inputs": {
        "statusCode": 200,
        "headers": {
          "Content-Type": "application/json"
        },
        "body": {
          "Status": "Accepted"
        }
      },
      "runAfter": {
        "Compose": [
          "Succeeded"
        ]
      }
    }
  },
  "else": {
    "actions": {
      "Compose_1": {
        "type": "Compose",
        "inputs": "Rejected"
      },
      "Response_1": {
        "type": "Response",
        "kind": "Http",
        "inputs": {
          "statusCode": 200,
          "headers": {
            "Content-Type": "application/json"
          },
          "body": {
            "status": "REJECTED"
          }
        },
        "runAfter": {
          "Compose_1": [
            "Succeeded"
          ]
        }
      }
    }
  },
  "runAfter": {
    "Compose2": [
      "Succeeded"
    ]
  }
}