AWSTemplateFormatVersion: '2010-09-09'
Description: HTTP API Gateway (SignalFx webhook) secured with auto-generated or custom Bearer token.

Parameters:
  WebhookBearerToken:
    Type: String
    NoEcho: true
    Default: ''
    Description: >
      Optional: Shared secret used as Bearer token (send as "Authorization: Bearer <token>").
      Leave blank to auto-generate a random token.

  LambdaRuntime:
    Type: String
    Default: python3.12
    AllowedValues: [python3.12, python3.11, python3.10, nodejs20.x, nodejs18.x]
    Description: Runtime for Lambda functions.

  RoutePath:
    Type: String
    Default: /signalfx
    Description: HTTP API route path for the webhook.

Resources:
  #####################################
  # Secret to auto-generate Bearer token if not supplied
  #####################################
  GeneratedBearerSecret:
    Type: AWS::SecretsManager::Secret
    Properties:
      Description: Auto-generated bearer token for SignalFx webhook
      GenerateSecretString:
        SecretStringTemplate: '{}'
        GenerateStringKey: bearerToken
        PasswordLength: 32
        ExcludePunctuation: true

  #####################################
  # Execution Roles
  #####################################
  WebhookHandlerRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: { Service: lambda.amazonaws.com }
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  AuthorizerRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: { Service: lambda.amazonaws.com }
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: ReadSecretBearer
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - secretsmanager:GetSecretValue
                Resource: !Ref GeneratedBearerSecret

  #####################################
  # Lambdas
  #####################################
  WebhookHandlerFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${AWS::StackName}-webhook-handler'
      Role: !GetAtt WebhookHandlerRole.Arn
      Runtime: !Ref LambdaRuntime
      Timeout: 15
      MemorySize: 256
      Handler: index.handler
      Code:
        ZipFile: |
          import json, logging
          logger = logging.getLogger()
          logger.setLevel(logging.INFO)

          def handler(event, context):
              logger.info("Event: %s", json.dumps(event))
              body = {}
              try:
                  raw = event.get("body") or ""
                  if event.get("isBase64Encoded"):
                      import base64
                      raw = base64.b64decode(raw).decode("utf-8")
                  body = json.loads(raw) if raw else {}
              except Exception:
                  logger.exception("Failed to parse body")

              return {
                  "statusCode": 200,
                  "headers": {"content-type": "application/json"},
                  "body": json.dumps({"ok": True, "received": bool(body)})
              }

  BearerAuthorizerFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub '${AWS::StackName}-bearer-authorizer'
      Role: !GetAtt AuthorizerRole.Arn
      Runtime: !Ref LambdaRuntime
      Timeout: 5
      MemorySize: 128
      Handler: index.handler
      Environment:
        Variables:
          EXPECTED_BEARER_PARAM: !Ref WebhookBearerToken
          SECRET_ARN: !Ref GeneratedBearerSecret
      Code:
        ZipFile: |
          import os, json, boto3

          sm = boto3.client("secretsmanager")

          def get_expected_token():
              # If user provided via parameter, use that
              val = os.environ.get("EXPECTED_BEARER_PARAM")
              if val and val.strip():
                  return val.strip()
              # Otherwise fetch from Secrets Manager
              secret_arn = os.environ["SECRET_ARN"]
              secret = sm.get_secret_value(SecretId=secret_arn)
              secret_str = json.loads(secret["SecretString"])
              return secret_str["bearerToken"]

          def handler(event, context):
              expected = "Bearer " + get_expected_token()
              headers = event.get("headers") or {}
              auth_hdr = headers.get("authorization") or headers.get("Authorization") or ""
              okay = (auth_hdr == expected)
              return {
                  "isAuthorized": okay,
                  "context": {
                      "reason": "authorized" if okay else "invalid_or_missing_bearer"
                  }
              }

  #####################################
  # HTTP API
  #####################################
  HttpApi:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      Name: !Sub '${AWS::StackName}-httpapi'
      ProtocolType: HTTP
      Description: SignalFx webhook endpoint secured with Bearer token.
      CorsConfiguration:
        AllowHeaders: ['*']
        AllowMethods: ['POST', 'OPTIONS']
        AllowOrigins: ['*']

  HttpIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref HttpApi
      IntegrationType: AWS_PROXY
      IntegrationMethod: POST
      PayloadFormatVersion: '2.0'
      TimeoutInMillis: 15000
      IntegrationUri: !Sub >
        arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${WebhookHandlerFunction.Arn}/invocations

  HttpAuthorizer:
    Type: AWS::ApiGatewayV2::Authorizer
    Properties:
      ApiId: !Ref HttpApi
      AuthorizerType: REQUEST
      Name: !Sub '${AWS::StackName}-bearer-authz'
      IdentitySource:
        - '$request.header.Authorization'
      AuthorizerPayloadFormatVersion: '2.0'
      EnableSimpleResponses: true
      AuthorizerUri: !Sub >
        arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${BearerAuthorizerFunction.Arn}/invocations

  HttpRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref HttpApi
      RouteKey: !Sub 'POST ${RoutePath}'
      Target: !Sub 'integrations/${HttpIntegration}'
      AuthorizationType: CUSTOM
      AuthorizerId: !Ref HttpAuthorizer

  HttpStage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref HttpApi
      StageName: '$default'
      AutoDeploy: true

  #####################################
  # Permissions
  #####################################
  InvokePermissionHandler:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunction
      FunctionName: !GetAtt WebhookHandlerFunction.Arn
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*/*/*

  InvokePermissionAuthorizer:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunction
      FunctionName: !GetAtt BearerAuthorizerFunction.Arn
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/authorizers/*

Outputs:
  ApiEndpoint:
    Description: Base URL for the HTTP API.
    Value: !GetAtt HttpApi.ApiEndpoint

  WebhookUrlHint:
    Description: Full webhook URL for SignalFx.
    Value: !Sub '${HttpApi.ApiEndpoint}${RoutePath}'

  GeneratedBearerToken:
    Description: Randomly generated bearer token (if not supplied).
    Value: !Sub '{{resolve:secretsmanager:${GeneratedBearerSecret}:SecretString:bearerToken}}'