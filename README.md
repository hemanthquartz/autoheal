AWSTemplateFormatVersion: '2010-09-09'
Description: ACE-DA | EMR on EKS Spark ETL with Step Functions (No EventBridge)

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
  AthenaDatabaseName:
    Type: String
    Default: ace_da_nyc_taxi
  StateMachineName:
    Type: String
    Default: ace-da-spark-etl-state-machine

Resources:

  ### IAM Role for Step Functions + EMR on EKS ###
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
                - states.amazonaws.com
                - emr-containers.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonS3FullAccess
        - arn:aws:iam::aws:policy/AmazonAthenaFullAccess
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
                  - states:StartExecution
                  - states:DescribeExecution
                  - states:GetExecutionHistory
                  - athena:StartQueryExecution
                  - athena:GetQueryExecution
                  - athena:GetQueryResults
                Resource: "*"

  ### Step Function State Machine ###
  SparkETLStateMachine:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineName: !Ref StateMachineName
      RoleArn: !GetAtt AceDaEMRExecutionRole.Arn
      DefinitionString:
        !Sub |
          {
            "Comment":"ACE-DA EMR on EKS Spark ETL",
            "StartAt":"CreateCluster",
            "States":{
              "CreateCluster":{
                "Type":"Task",
                "Resource":"arn:aws:states:::emr-containers:createVirtualCluster",
                "Parameters":{
                  "Name":"ace-da-virtual-cluster-${AWS::StackName}",
                  "ContainerProvider":{
                    "Id":"${EKSClusterName}",
                    "Type":"EKS",
                    "Info":{"EksInfo":{"Namespace":"${EKSNamespace}"}}
                  }
                },
                "ResultPath":"$.Cluster",
                "Next":"SubmitSparkJob"
              },
              "SubmitSparkJob":{
                "Type":"Task",
                "Resource":"arn:aws:states:::emr-containers:startJobRun.sync",
                "Parameters":{
                  "Name":"ace-da-spark-job-${AWS::StackName}",
                  "VirtualClusterId.$":"$.Cluster.Id",
                  "ExecutionRoleArn":"${AceDaEMRExecutionRoleArn}",
                  "ReleaseLabel":"emr-6.6.0-latest",
                  "JobDriver":{
                    "SparkSubmitJobDriver":{
                      "EntryPoint":"s3://${S3BucketInput}/scripts/nyc_taxi_etl.py",
                      "SparkSubmitParameters":"--conf spark.executor.instances=2"
                    }
                  },
                  "ConfigurationOverrides":{
                    "MonitoringConfiguration":{
                      "S3MonitoringConfiguration":{"LogUri":"s3://${S3BucketOutput}/logs/"}
                    }
                  }
                },
                "ResultPath":"$.Job",
                "Next":"DeleteCluster"
              },
              "DeleteCluster":{
                "Type":"Task",
                "Resource":"arn:aws:states:::emr-containers:deleteVirtualCluster.sync",
                "Parameters":{"Id.$":"$.Cluster.Id"},
                "Next":"CreateAthenaTable"
              },
              "CreateAthenaTable":{
                "Type":"Task",
                "Resource":"arn:aws:states:::athena:startQueryExecution.sync",
                "Parameters":{
                  "QueryString": {
                    "Fn::Sub": [
                      "CREATE EXTERNAL TABLE IF NOT EXISTS ${AthenaDB}.nyc_taxi_avg_summary(type string, avgDist double, avgCostPerMile double, avgCost double) ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe' STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat' LOCATION 's3://${S3BucketOutput}/output/' TBLPROPERTIES ('classification'='parquet','compressionType'='none','typeOfData'='file')",
                      { "AthenaDB":{ "Ref":"AthenaDatabaseName" } }
                    ]
                  },
                  "ResultConfiguration":{
                    "OutputLocation":"s3://${S3BucketOutput}/athena/results/"
                  }
                },
                "End": true
              }
            }
          }

Outputs:
  AceDaStepFunctionArn:
    Description: ARN of the ACE-DA Spark ETL Step Function
    Value: !Ref SparkETLStateMachine

  AceDaEMRExecutionRoleArn:
    Description: IAM Role ARN for Step Functions and EMR on EKS
    Value: !GetAtt AceDaEMRExecutionRole.Arn