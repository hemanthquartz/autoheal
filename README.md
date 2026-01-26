import os
          import json
          import boto3

          ssm = boto3.client("ssm")

          def _get(d, path, default=None):
              cur = d
              for p in path.split("."):
                  if not isinstance(cur, dict) or p not in cur:
                      return default
                  cur = cur[p]
              return cur

          def handler(event, context):
              # Expected event shape (from EventBridge):
              # event["detail"] = {"instanceId": "...", "runAsUser": "...", "command": "..."}
              print("EVENT:", json.dumps(event))

              detail = event.get("detail") or {}

              instance_id = detail.get("instanceId") or os.environ.get("DEFAULT_INSTANCE_ID")
              run_as_user = detail.get("runAsUser") or os.environ.get("DEFAULT_RUN_AS_USER")
              command = detail.get("command")

              if not instance_id:
                  raise ValueError("Missing instanceId. Provide detail.instanceId or set DefaultInstanceId in the stack.")
              if not command:
                  raise ValueError("Missing command. Provide detail.command (example: sendevent -E STARTJOB -J <JOB_NAME>).")

              document_name = os.environ.get("DOCUMENT_NAME")

              # Your SSM document expects these parameter names:
              # - command
              # - runAsUser
              resp = ssm.send_command(
                  DocumentName=document_name,
                  InstanceIds=[instance_id],
                  Parameters={
                      "command": [command],
                      "runAsUser": [run_as_user]
                  },
                  Comment=f"Autosys trigger via {document_name}"
              )

              command_id = resp["Command"]["CommandId"]
              print("SSM CommandId:", command_id)

              return {
                  "ok": True,
                  "instanceId": instance_id,
                  "documentName": document_name,
                  "runAsUser": run_as_user,
                  "command": command,
                  "commandId": command_id
              }
