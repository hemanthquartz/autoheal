# AWS Single Account Onboarding Guide for Splunk Data Manager

This guide provides a detailed, step-by-step process for onboarding a single AWS account into Splunk Data Manager to ingest data into Splunk Cloud Platform. It covers prerequisites, role and policy creation, configuration steps, CloudFormation template deployment, verification, and editing data inputs. The instructions are based on the Splunk Cloud Platform documentation for Data Manager version 1.13.

---

## Prerequisites

Before starting, ensure the following requirements are met:

1. **Splunk Cloud Platform Access**:
   - You have a Splunk Cloud Platform instance running version 8.2.2104.1 or higher on the Victoria or Classic Experience.
   - Data Manager is available in supported AWS regions (e.g., US East Virginia, US West Oregon, UK London, Europe Dublin, Frankfurt, Paris, Asia Pacific Singapore, Sydney, Tokyo, Canada Central). Check the Splunk Cloud Platform Service Description for region availability.[](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-manager-user-manual/1.12/introduction/about-data-manager)[](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-manager-user-manual/1.13/getting-data-in-gdi/set-up-data-manager)
   - Log in to Splunk Cloud using Splunk-provided credentials. Save the email containing the credentials, as it includes a "Forgot Password" link. Change your password when prompted and sign the terms and conditions.[](https://docs.splunk.com/Documentation/DM/latest/User/AWSAbout)

2. **AWS Account Requirements**:
   - You have a valid AWS account with administrative permissions to configure AWS services and create IAM roles and users.
   - If you lack these permissions, collaborate with your organization’s AWS administrator.
   - Ensure port 443 is open for HTTPS REST API calls used by Splunk Data Manager.[](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-manual/9.3.2408/get-data-into-splunk-cloud-platform/get-amazon-web-services-aws-data-into-splunk-cloud-platform)

3. **User Role Capabilities**:
   - The Splunk Cloud user must have either the `admin` or `sc_admin` role, or a custom role with the following capabilities:
     - `accelerate_search`, `admin_all_objects`, `dmc_deploy_apps`, `dmc_deploy_token_http`, `edit_httpauths`, `edit_sourcetypes`, `edit_token_http`, `edit_view_html`, `get_metadata`, `get_typeahead`, `indexes_edit`, `indexes_list_all`, `list_accelerate_search`, `list_httpauths`, `list_inputs`, `list_settings`, `list_storage_passwords`, `list_tokens_own`, `list_tokens_scs`, `output_file`, `rest_apps_management`, `rest_properties_get`, `rest_properties_set`, `run_collect`, `run_mcollect`, `schedule_rtsearch`, `schedule_search`, `search`.[](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-manager-user-manual/1.13/getting-data-in-gdi/set-up-data-manager)[](https://docs.splunk.com/Documentation/DM/1.13.0/User/Setup)
   - Data Manager is only available on the primary search head of your Splunk Cloud deployment. Contact your Splunk Cloud administrator to identify the primary search head.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/Setup)

4. **AWS CLI or Console Access**:
   - Prepare a terminal or AWS Management Console to apply CloudFormation templates and manage IAM roles. Ensure AWS CLI is configured with credentials that have permissions to run commands against your AWS account.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSSingleAccount)

5. **Indexes**:
   - Create a test index in Splunk Cloud Platform to validate data ingestion before production. Follow the instructions in the Splunk Cloud Platform documentation to create an index.[](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-manual/9.3.2408/get-data-into-splunk-cloud-platform/get-amazon-web-services-aws-data-into-splunk-cloud-platform)

---

## Overview of Onboarding Process

Onboarding a single AWS account in Data Manager involves three main stages:

1. **Configure AWS Prerequisites**: Set up the necessary IAM roles and policies in the AWS account.
2. **Configure Data Account and Data Sources**: Specify the AWS account, regions, and data sources in Data Manager.
3. **Deploy CloudFormation Stack**: Apply a CloudFormation stack in each region to enable data ingestion.

Data Manager supports AWS data sources such as AWS CloudTrail, AWS GuardDuty, Security Hub, IAM Access Analyzer, IAM Credential Report, and Metadata, enabling ingestion from over 100 AWS services.[](https://www.splunk.com/en_us/blog/platform/meet-the-data-manager-for-splunk-cloud.html)

---

## Step-by-Step Onboarding Process

### Step 1: Configure AWS Prerequisites

You need to create an IAM role (`SplunkDMReadOnly`) to allow Splunk Cloud to read metadata from AWS services such as CloudTrail, Security Hub, GuardDuty, CloudFormation, Kinesis Data Firehose, S3, Lambda, CloudWatch Events, and CloudWatch Logs.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)

#### 1.1 Create the SplunkDMReadOnly Role

1. **Log into the AWS Management Console**:
   - Use an account with IAM administrative permissions.

2. **Navigate to IAM**:
   - Go to **IAM > Roles** in the AWS Console.

3. **Create a New Role**:
   - Click **Create role**.
   - Select **AWS account** under **Trusted entity type**.
   - Choose **Another AWS account**.
   - In the **Account ID** field, enter the Splunk Cloud Platform account ID provided in the Data Manager UI (e.g., `123456789012`). You can find this in the **Trust Relationship** statement in Data Manager.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSOrganizations)[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSSingleAccount)
   - Under **Options**, select **Require external ID**.
   - In the **External ID** field, paste the `sts:ExternalId` from the **Trust Relationship** in Data Manager (e.g., `ffcbd123-1a234-123b-12c3-1234567890b`).[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSOrganizations)
   - Click **Next**.

4. **Skip Permissions for Now**:
   - On the **Add permissions** page, click **Next** (you will add an inline policy later).

5. **Name the Role**:
   - On the **Name, review, and create** page, enter `SplunkDMReadOnly` in the **Role Name** field.
   - Click **Create role**.

6. **Add an Inline Policy**:
   - Select the newly created `SplunkDMReadOnly` role from the Roles list.
   - Under the **Permissions** tab, click **Add inline policy**.
   - Click the **JSON** tab.
   - Copy and paste the **Role Policy** JSON from the Data Manager UI. This policy grants read-only access to metadata from AWS services.
   - Click **Review policy**.
   - In the **Name** field, enter a name (e.g., `SplunkDMReadOnlyPolicy`).
   - Click **Create policy**.

#### 1.2 (Optional) Create an IAM User for Onboarding

If you prefer to use an IAM user instead of a role for onboarding, follow these steps:

1. **Navigate to IAM Users**:
   - Go to **IAM > Users** in the AWS Console.
   - Click **Add user**.

2. **Configure the User**:
   - In the **User name** field, enter a name (e.g., `OnboardingUser`).
   - For **Access type**, select **AWS Management Console access**.
   - Choose a **Console password** option (e.g., custom password or auto-generated).
   - Check **User must create a new password at next sign-in** if desired.
   - Click **Next: Permissions**.

3. **Create a Policy**:
   - Click **Attach existing policies directly** > **Create policy**.
   - In the new window, click the **JSON** tab.
   - Copy and paste the **Permissions** JSON from the Data Manager UI.
   - Replace any `<DATA_ACCOUNT_ID>` placeholders with your AWS account ID.
   - Click **Next: Tags** > **Next: Review**.
   - In the **Name** field, enter a policy name (e.g., `OnboardingUserPolicy`).
   - Click **Create policy**.

4. **Attach the Policy**:
   - Return to the **Add user** page and click the refresh icon.
   - In the **Filter policies** field, search for your policy (e.g., `OnboardingUserPolicy`).
   - Select the policy checkbox.
   - Click **Next: Tags** > **Next: Review** > **Create user**.

5. **Update Trust Relationship**:
   - If required, update the trust relationship for the `SplunkDMReadOnly` role:
     - Navigate to **IAM > Roles** > **SplunkDMReadOnly** > **Trust relationships** tab.
     - Click **Edit trust policy**.
     - Copy and paste the **Trust Relationship** JSON from the Data Manager UI, replacing `<DATA_ACCOUNT_ID>` with your AWS account ID.
     - Click **Update policy**.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSSingleAccount)

#### 1.3 Configure SQS and S3 Resources

1. **Create an SQS Queue**:
   - Go to **AWS Management Console > Application Integration > Simple Queue Service**.
   - Click **Create queue**.
   - Enter a name (e.g., `cloudtrail-dlq`).
   - Select **Standard Queue** and click **Create Queue**.
   - From the queue list, select your queue and click **Queue Actions** > **Configure Queue**.
   - In **Dead Letter Queue Settings**, select **Use Redrive Policy**.
   - In the **Dead Letter Queue** field, enter the queue name (e.g., `cloudtrail-dlq`).
   - In **Maximum receives**, enter `3`.
   - Click **Save Changes**.[](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-manual/9.3.2408/get-data-into-splunk-cloud-platform/get-amazon-web-services-aws-data-into-splunk-cloud-platform)

2. **Provide SQS Queue ARNs and S3 Bucket Names**:
   - In the Data Manager UI, input the AWS SQS Queue ARNs, Data Account IDs, and S3 bucket names as prompted during the configuration stage.[](https://docs.splunk.com/Documentation/DM/latest/User/AWSAbout)

---

### Step 2: Configure Data Account, Regions, and Data Sources

1. **Log into Splunk Cloud**:
   - Access the Splunk Cloud Platform and navigate to the Data Manager app on the primary search head.

2. **Start Onboarding**:
   - In Data Manager, select **AWS** as the cloud provider and choose **Single Account** onboarding.
   - Enter the AWS Account ID for the account you configured in Step 1.
   - Select the AWS regions for data ingestion (e.g., us-east-1, us-west-2). Note that us-east-1 is used for IAM roles and other resources, even if not selected for data ingestion.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)
   - Choose data sources (e.g., AWS CloudTrail, GuardDuty, Security Hub, IAM Access Analyzer, IAM Credential Report, Metadata). You can assign each data source to a different Splunk index.[](https://www.splunk.com/en_us/blog/platform/meet-the-data-manager-for-splunk-cloud.html)

3. **Review Configuration**:
   - Verify the account ID, regions, and data sources in the Data Manager UI.
   - Data Manager will generate HTTP Event Collector (HEC) tokens for each dataset. The template download button remains disabled until all tokens are created, indicated by a status banner in the UI.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)

---

### Step 3: Deploy CloudFormation Stack

1. **Download CloudFormation Template**:
   - In Data Manager, once the HEC tokens are created, the template download button will be enabled.
   - Download the CloudFormation template provided by Data Manager. This template creates resources like IAM roles, S3 buckets, Kinesis Data Firehose, and CloudWatch Logs for data ingestion.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)

2. **Apply the Template**:
   - **Using AWS Console**:
     - Go to **AWS Management Console > CloudFormation > Stacks**.
     - Click **Create stack** > **With new resources (standard)**.
     - Upload the downloaded template file.
     - Specify a stack name (e.g., `SplunkDMDataIngestion`).
     - Follow the prompts to configure stack options (leave defaults unless specific requirements exist).
     - Review and click **Create stack**.
   - **Using AWS CLI**:
     - Run the following command, replacing `<template-file>` with the path to the downloaded template and `<stack-name>` with your stack name:
       ```bash
       aws cloudformation create-stack --stack-name <stack-name> --template-body file://<template-file> --capabilities CAPABILITY_NAMED_IAM
       ```
     - The `--capabilities CAPABILITY_NAMED_IAM` flag is required to create IAM resources.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSSingleAccount)
   - Repeat this process for each selected region.

3. **Monitor Stack Creation**:
   - In the AWS Console, monitor the stack status in **CloudFormation > Stacks**.
   - The stack creates resources like IAM roles, S3 buckets, Kinesis Data Firehose, and CloudWatch Logs subscriptions. Data should start flowing within five minutes of stack creation.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)

---

## Verify Data Input

1. **Check Data Manager UI**:
   - In Data Manager, navigate to the **Data Input Details** tab and go to the **Account Establishment Details** section.
   - Verify the input status. An “In Progress” status indicates the input is still provisioning. A “Success” status with updating “Throughput” and “Last Received” fields confirms active data ingestion.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

2. **AWS CloudTrail Verification**:
   - If ingesting CloudTrail data, ensure CloudTrail is enabled and configured to send logs to CloudWatch in the selected AWS region.
   - In AWS, navigate to **CloudTrail** and select the trail. Verify the **CloudWatch Logs** log group is configured.
   - Go to **CloudWatch > Log groups**, select the log group, and under **Subscription filters**, confirm the destination ARN points to the Kinesis Firehose delivery stream (`SplunkDMCloudTrailDeliveryStream`).
   - In AWS, navigate to **Kinesis > Delivery streams**, select `SplunkDMCloudTrailDeliveryStream`, and verify the status is active. Confirm the source record transformation uses `SplunkDMCloudWatchLogProcessor` as the Lambda function.[](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-manager-troubleshooting-manual/1.13/troubleshoot-aws-data-ingestion/troubleshoot-aws-cloudtrail-data-ingestion)

3. **AWS Inputs Health Dashboard**:
   - In Data Manager, use the **AWS Inputs Health** dashboard to monitor input status by data source and account. Filter inputs to verify they match your configuration plan.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

4. **Event Count Validation**:
   - If migrating from another input method (e.g., Splunk Add-on for AWS), compare event counts between the legacy input and Data Manager to ensure consistency. Use Splunk searches to count events by source. If counts differ, investigate potential duplicate data sources or misconfigurations.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

5. **Troubleshooting**:
   - If data is not flowing, check for missing or misconfigured AWS resources (e.g., IAM roles, SQS queues, or Kinesis Firehose).
   - Delete the data input in Data Manager and recreate it if necessary.
   - Refer to the Data Manager Troubleshooting Manual for additional guidance.[](https://help.splunk.com/en/splunk-cloud-platform/ingest-data-from-cloud-services/data-manager-troubleshooting-manual/1.13/troubleshoot-aws-data-ingestion/troubleshoot-aws-cloudtrail-data-ingestion)

---

## Edit AWS Data Inputs

1. **Access Data Inputs**:
   - In Data Manager, go to the **Data Inputs** tab and select the AWS input you want to edit.

2. **Modify Configuration**:
   - Update the AWS account ID, regions, or data sources as needed.
   - Note that editing may require updating the CloudFormation stack. Data Manager will generate a new template if changes are made.

3. **Update CloudFormation Stack**:
   - Download the updated template from Data Manager.
   - In AWS, go to **CloudFormation > Stacks**, select the existing stack, and click **Update**.
   - Choose **Replace current template** and upload the new template.
   - Review changes and click **Update stack**.
   - Alternatively, use the AWS CLI:
     ```bash
     aws cloudformation update-stack --stack-name <stack-name> --template-body file://<new-template-file> --capabilities CAPABILITY_NAMED_IAM
     ```

4. **Verify Changes**:
   - Confirm the updated stack status in AWS CloudFormation.
   - Check the Data Manager **AWS Inputs Health** dashboard to ensure data is flowing correctly.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

---

## Additional Notes

- **Cost Considerations**:
  - Deploying CloudFormation templates and AWS services (e.g., S3, Kinesis, CloudWatch) incurs costs. Use the AWS Pricing Calculator to estimate expenses.[](https://docs.splunk.com/Documentation/SVA/current/Architectures/AWSGDI)
  - Avoid duplicate data ingestion to prevent unnecessary licensing and cost increases.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

- **Best Practices**:
  - Use infrastructure as code (CloudFormation) for consistent deployment.[](https://docs.splunk.com/Documentation/SVA/current/Architectures/AWSGDI)
  - Regularly monitor the **AWS Inputs Health** dashboard to ensure input health.
  - If onboarding additional AWS accounts later, ensure no overlapping data accounts or input types to avoid conflicts.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSOrganizations)

- **Security**:
  - The `SplunkDMReadOnly` role provides read-only access to metadata, ensuring secure data ingestion. Review the role policy in Data Manager before applying it.[](https://docs.splunk.com/Documentation/DM/1.13.0/User/AWSSingleAccount)
  - Use the Splunk Security Analytics for AWS dashboards to monitor data breaches, misconfigurations, insider threats, and user activity after onboarding.[](https://docs.splunk.com/Documentation/DM/1.0.0/User/StartConfiguration)

- **Support**:
  - For issues, contact Splunk Support or refer to the Splunk Community for guidance.[](https://www.splunk.com/en_us/blog/platform/meet-the-data-manager-for-splunk-cloud.html)
  - If using the Splunk Add-on for AWS as a legacy method, consider transitioning to Data Manager for simplified management.[](https://lantern.splunk.com/Data_Descriptors/Amazon/Migrating_AWS_inputs_to_Data_Manager)

---

## Attachments

The following files provide the IAM role policy, trust relationship, and a sample CloudFormation template. These are placeholders and should be replaced with the actual JSON provided by the Data Manager UI.

<xaiArtifact artifact_id="4dce3a6a-bf08-43ea-9201-00eb96806655" artifact_version_id="857a27b6-65dd-41f3-88e7-db3d540489da" title="SplunkDMReadOnly_Policy.json" contentType="application/json">
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudtrail:DescribeTrails",
        "securityhub:GetFindings",
        "guardduty:ListDetectors",
        "cloudformation:DescribeStacks",
        "kinesis:DescribeStream",
        "s3:GetBucketLocation",
        "lambda:GetFunction",
        "cloudwatch:DescribeLogGroups",
        "cloudwatch:GetMetricData"
      ],
      "Resource": "*"
    }
  ]
}