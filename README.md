AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: ACE-DA | Dynamic EMR on EKS Job Config via S3 EventBridge + SQS + Lambda (SAM) + Step Function

Parameters:
  EKSClusterName:
    Type: String
    Default: ace-da-eks-cluster
  EKSNamespace:
    Type: String
    Default: ace-da-namespace
  S3BucketInput:
    Type: String
    Default: ace-da-input-bucket
  S3BucketOutput:
    Type: String
    Default: ace-da-output-bucket
  StateMachineName:
    Type: String
    Default: ace-da-spark-etl-state-machine

Resources:

  ### DynamoDB Table ###
  JobConfigTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: ace-da-job-config
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: JobName
          AttributeType: S
      KeySchema:
        - AttributeName: JobName
          KeyType: HASH

  ### EMR Execution Role ###
  AceDaEMRExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: ace-da-emr-execution-role
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service:
                - emr-containers.amazonaws.com
                - states.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonS3FullAccess
        - arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly
        - arn:aws:iam::aws:policy/AmazonElasticMapReduceFullAccess
        - arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole
        - arn:aws:iam::aws:policy/CloudWatchLogsFullAccess
      Policies:
        - PolicyName: ace-da-emr-on-eks-inline
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - eks:DescribeCluster
                  - iam:PassRole
                  - emr-containers:*
                Resource: "*"
              - Effect: Allow
                Action:
                  - iam:CreateServiceLinkedRole
                Resource: "*"
                Condition:
                  StringEquals:
                    iam:AWSServiceName: "emr-containers.amazonaws.com"
      Tags:
        - Key: for-use-with-amazon-emr-managed-policies
          Value: true

  ### Step Function (remains unchanged) ###
  SparkETLStateMachine:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineName: !Ref StateMachineName
      RoleArn: "arn:aws:iam::064603859039:role/eksworkshop-admin"
      DefinitionString:
        !Sub |
          {
            "Comment": "ACE-DA EMR on EKS Spark ETL (Dynamic Config)",
            "StartAt": "SubmitSparkJob",
            "States": {
              "SubmitSparkJob": {
                "Type": "Task",
                "Resource": "arn:aws:states:::emr-containers:startJobRun.sync",
                "Parameters": {
                  "Name.$": "$.JobName",
                  "VirtualClusterId.$": "$.VirtualClusterId",
                  "ExecutionRoleArn": "arn:aws:iam::064603859039:role/emr-eks-fargate-emr-data-team-a",
                  "ReleaseLabel.$": "$.ReleaseLabel",
                  "JobDriver": {
                    "SparkSubmitJobDriver": {
                      "EntryPoint.$": "$.PyFilePath",
                      "SparkSubmitParameters.$": "$.SparkSubmitParameters"
                    }
                  },
                  "ConfigurationOverrides": {
                    "MonitoringConfiguration": {
                      "S3MonitoringConfiguration": {
                        "LogUri.$": "$.LogUri"
                      }
                    }
                  }
                },
                "End": true
              }
            }
          }

  ### EventBridge Rule ###
  S3PutEventRule:
    Type: AWS::Events::Rule
    Properties:
      Name: ace-da-s3-putobject-eventbridge-rule2
      EventPattern:
        source:
          - aws.s3
        detail-type:
          - AWS API Call via CloudTrail
        detail:
          eventName:
            - PutObject
            - CopyObject
            - PostObject
            - CompleteMultipartUpload
        requestParameters:
          bucketName:
            - "ace-da-input-bucket"
          key:
            - wildcard: !Sub green/*.parquet
      Targets:
        - Arn: !GetAtt S3EventQueue.Arn
          Id: "SQSQueueTarget"
          RoleArn: !GetAtt EventBridgeToSQSTargetRole.Arn

  ### SQS Queue ###
  S3EventQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: ace-da-s3-event-queue

  S3EventQueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref S3EventQueue
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal: "*"
            Action: "sqs:SendMessage"
            Resource: !GetAtt S3EventQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !GetAtt S3PutEventRule.Arn

  ### EventBridge to SQS Role ###
  EventBridgeToSQSTargetRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: ace-da-eb-to-sqs-role
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: AllowPutToSQS
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: sqs:SendMessage
                Resource: !GetAtt S3EventQueue.Arn

  ### Lambda Role for SQS-triggered Lambda ###
  ProcessS3EventLambdaRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: ace-da-process-s3-lambda-role
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: AllowDynamoDBAndStepFunction
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - dynamodb:GetItem
                Resource: !GetAtt JobConfigTable.Arn
              - Effect: Allow
                Action:
                  - states:StartExecution
                Resource: !Ref SparkETLStateMachine

  ### Lambda: Only one Lambda, triggered by SQS, fetches config and invokes Step Function ###
  ProcessS3EventLambda:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: ace-da-process-s3-event
      Runtime: python3.9
      Role: "arn:aws:iam::064603859039:role/eksworkshop-admin"
      Handler: index.lambda_handler
      Timeout: 30
      InlineCode: |
        import json
        import boto3

        def lambda_handler(event, context):
            for record in event['Records']:
                message_body = json.loads(record['body'])
                detail = message_body.get("detail", {})
                bucket_name = detail.get("bucket", {}).get("name")
                object_key = detail.get("object", {}).get("key")
                # You can extract job_name from S3 key or other logic
                job_name = object_key.split("/")[0] if object_key else "nyc-taxi-job"
                ddb = boto3.resource("dynamodb")
                table = ddb.Table("ace-da-job-config")
                job_config = table.get_item(Key={"JobName": job_name}).get("Item")
                if not job_config:
                    raise Exception(f"No config found for {job_name}")
                # Optionally, pass in additional info from S3 event if desired
                job_config['S3Bucket'] = bucket_name
                job_config['S3Key'] = object_key
                step_fn = boto3.client("stepfunctions")
                response = step_fn.start_execution(
                    stateMachineArn="${SparkETLStateMachine}",
                    input=json.dumps(job_config)
                )
                print("Step Function started:", response["executionArn"])
            return {"status": "started"}
      Events:
        SQSEvent:
          Type: SQS
          Properties:
            Queue: !GetAtt S3EventQueue.Arn
            BatchSize: 1
            Enabled: true
            MaximumBatchingWindowInSeconds: 5



Outputs:
  StepFunctionArn:
    Description: "ARN of the Step Function"
    Value: !Ref SparkETLStateMachine
  EventLambdaArn:
    Description: "ARN of the Lambda triggered by SQS"
    Value: !GetAtt ProcessS3EventLambda.Arn
  DynamoDBTableName:
    Description: "Name of the DynamoDB Table"
    Value: !Ref JobConfigTable
  EventQueueURL:
    Description: "URL of the SQS Queue"
    Value: !Ref S3EventQueue





###################################################################################################

AWSTemplateFormatVersion: "2010-09-09"
Description: CloudFormation template for insurance data processing resources

Resources:
  InsuranceProcessingStatusTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: InsuranceProcessingStatus
      AttributeDefinitions:
        - AttributeName: TableName
          AttributeType: S
      KeySchema:
        - AttributeName: TableName
          KeyType: HASH
      BillingMode: PAY_PER_REQUEST

  LambdaExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: LambdaDynamoDBAccess
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - dynamodb:GetItem
                  - dynamodb:PutItem
                  - dynamodb:UpdateItem
                  - dynamodb:DeleteItem
                Resource: !GetAtt InsuranceProcessingStatusTable.Arn
              - Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: "*"

  InitializeStatusFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: InitializeStatusFunction
      Handler: index.lambda_handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        ZipFile: |
          import json
          import boto3

          dynamodb = boto3.resource("dynamodb")
          table = dynamodb.Table("InsuranceProcessingStatus")

          def lambda_handler(event, context):
              tables = event["Tables"]
              for table_name in tables:
                  table.put_item(
                      Item={
                          "TableName": table_name,
                          "Status": "PENDING"
                      }
                  )
              return {
                  "statusCode": 200,
                  "body": json.dumps({"message": "Status initialized"})
              }
      Runtime: python3.9
      Timeout: 30

  UpdateStatusFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: UpdateStatusFunction
      Handler: index.lambda_handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        ZipFile: |
          import json
          import boto3

          dynamodb = boto3.resource("dynamodb")
          table = dynamodb.Table("InsuranceProcessingStatus")

          def lambda_handler(event, context):
              table_name = event["TableName"]
              status = event["Status"]
              
              table.update_item(
                  Key={"TableName": table_name},
                  UpdateExpression="SET #status = :status",
                  ExpressionAttributeNames={"#status": "Status"},
                  ExpressionAttributeValues={":status": status}
              )
              
              return {
                  "statusCode": 200,
                  "body": json.dumps({"message": f"Updated status for {table_name} to {status}"})
              }
      Runtime: python3.9
      Timeout: 30

  CheckStatusFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: CheckStatusFunction
      Handler: index.lambda_handler
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        ZipFile: |
          import json
          import boto3

          dynamodb = boto3.resource("dynamodb")
          table = dynamodb.Table("InsuranceProcessingStatus")

          def lambda_handler(event, context):
              table_names = event.get("TableNames", [event.get("TableName")])
              
              all_completed = True
              for table_name in table_names:
                  response = table.get_item(Key={"TableName": table_name})
                  item = response.get("Item", {})
                  status = item.get("Status", "PENDING")
                  if status != "COMPLETED":
                      all_completed = False
              
              if len(table_names) == 1:
                  return {
                      "statusCode": 200,
                      "Status": status
                  }
              else:
                  return {
                      "statusCode": 200,
                      "AllCompleted": all_completed
                  }
      Runtime: python3.9
      Timeout: 30

#############################################################################################
