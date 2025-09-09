AWSTemplateFormatVersion: '2010-09-09'
Description: >
  EMR on EKS Virtual Cluster and Execution Role for data-team-a (with IRSA support for multiple namespaces)

Parameters:
  ClusterName:
    Type: String
    Description: EKS Cluster name (must match EKS::Cluster::Name)

Resources:
  EmrExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub "${ClusterName}-emr-data-team-a"
      Description: EMR Execution Role for emr-data-team-a (supports IRSA for multiple teams)
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Sid: EMR
            Effect: Allow
            Principal:
              Service: elasticmapreduce.amazonaws.com
            Action: sts:AssumeRole

          - Sid: IRSA
            Effect: Allow
            Principal:
              Federated: arn:aws:iam::064603859039:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/4FE5345D95E91A60E436CAFE3A4AD4EA
            Action: sts:AssumeRoleWithWebIdentity
            Condition:
              StringEquals:
                oidc.eks.us-east-1.amazonaws.com/id/4FE5345D95E91A60E436CAFE3A4AD4EA:aud: sts.amazonaws.com
              StringLike:
                oidc.eks.us-east-1.amazonaws.com/id/4FE5345D95E91A60E436CAFE3A4AD4EA:sub: system:serviceaccount:emr-data-team-a:emr-containers-sa-*-*-064603859039-*

          - Effect: Allow
            Principal:
              Federated: arn:aws:iam::064603859039:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/4FE5345D95E91A60E436CAFE3A4AD4EA
            Action: sts:AssumeRoleWithWebIdentity
            Condition:
              StringLike:
                oidc.eks.us-east-1.amazonaws.com/id/4FE5345D95E91A60E436CAFE3A4AD4EA:sub: system:serviceaccount:emr-data-team-b:emr-containers-sa-*-*-064603859039-csq0syvldn3aflco8bfkqrhssu3rfs8dfycg0va8zeg5ihcx

      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonS3FullAccess
      Tags:
        - Key: Name
          Value: emr-data-team-a

  EmrVirtualCluster:
    Type: AWS::EMRContainers::VirtualCluster
    Properties:
      Name: !Sub "${ClusterName}-emr-data-team-a"
      ContainerProvider:
        Type: EKS
        Id: !Ref ClusterName
        Info:
          EksInfo:
            Namespace: emr-data-team-a

Outputs:
  VirtualClusterId:
    Value: !Ref EmrVirtualCluster
  VirtualClusterArn:
    Value: !GetAtt EmrVirtualCluster.Arn
  JobExecutionRoleArn:
    Value: !GetAtt EmrExecutionRole.Arn
