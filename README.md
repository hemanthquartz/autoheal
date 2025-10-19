  HttpIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref HttpApi
      IntegrationType: AWS_PROXY
      IntegrationMethod: POST
      IntegrationUri: !Sub >
        arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${WebhookHandlerFunction.Arn}/invocations
      PayloadFormatVersion: '2.0'


  LambdaPermissionApiGateway:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunction
      FunctionName: !GetAtt WebhookHandlerFunction.Arn
      Principal: apigateway.amazonaws.com
      SourceArn: !Sub arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*