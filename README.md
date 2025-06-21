AWSTemplateFormatVersion: '2010-09-09'
Transform: 'AWS::Serverless-2016-10-31'
Description: Onprem Bridge Resiliency Automation
Resources:

  lxmldbpython312:
    Type: AWS::Serverless::LayerVersion
    Properties:
      LayerName: 'fundancitg-python312-oracledb-lxml-V2'
      Description: 'lxml Layer for samefactored V2'
      ContentUri: config/fundancitg-python312-oracledb-lxml.zip
      CompatibleRuntimes:
        - python3.12
      RetentionPolicy: Retain

  LayerVersionParameter:
    Type: AWS::SSM::Parameter
    Properties:
      Name: '/layers/fundancitg-python312-oracledb-lxml/latest'
      Description: 'Stores the latest ARN of the Lambda Layer fundancitg-python312-oracledb-lxml-V2'
      Type: String
      Value: !Ref lxmldbpython312