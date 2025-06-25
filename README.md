AWS Single Account Onboarding to Splunk Data Manager

1. Overview and Prerequisites
Ensure you have admin access to your AWS account. Confirm this is a single-account setup with no conflicting IAM policies.

2. Splunk Data Manager Initial Setup
Follow these initial steps in the Splunk Cloud Data Manager:

1. In Splunk Cloud, navigate to 'Data Manager' under Apps.

2. Click on 'New Data Input', select 'AWS', then click 'Next'.

3. Select your AWS data sources for onboarding.

4. Choose 'Single Account' and click 'Next'.

3. Input Amazon CloudWatch Logs Data Information
Provide details for CloudWatch Logs ingestion:

- Enter a descriptive 'Data Input Name'.

- Enter your AWS Account ID (12-digit number).

- Select the AWS services and specify destinations.

- Select the IAM Roles Region and AWS Regions from which logs will be ingested.

- Review data input and click 'Next'.

4. Setup Data Ingestion
Choose a Method to Run the Template on Your Accounts and Regions (AWS Console)

Complete the following steps in the AWS Console:

 

1. Log into your AWS account and navigate to the CloudFormation Service.

  ▶ Add IAM Region (10 steps)

 

2. Select the region of us-east-1. Do not use a different region first:

  AWS Console for us-east-1 ▶

 

3. Click Create stack, and select With new resources from the drop-down list.

  3.1 Under Prepare template, select Template is ready.

  3.2 Under Specify Template, select Upload a template file.

  3.3 Select Choose file and select the previously downloaded template.

  3.4 Click Next.

 

4. Enter the Stack Name of SplunkDMDataIngest-9643f204-bc7b-4c66-8245-55238b98f99a

 

5. Leave Parameters as No parameters.

 

6. Click Next.

 

7. Specify Tags.

  7.1 Enter the Key of SplunkDMVersion

  7.2 Enter the Value of 1

 

8. Click Next.

 

9. Review your entries.

 

10. Check the box under Capabilities to provide your acknowledgement.

 

11. Click Submit. Wait for the stack to have the CREATE_COMPLETE status to indicate that it is created successfully.

5. Name the stack appropriately (e.g., SplunkDMDataIngest).

6. Add a tag 'SplunkDMVersion' if required.

7. Proceed through prompts and acknowledge capabilities.

8. Click 'Submit' and wait for CREATE_COMPLETE status.

5. IAM Role Creation
After the above setup, create the IAM Role:

Role name: 'SplunkDataManagerRole-SingleAccount'

- IAM Console → Roles → Create role → Another AWS account.

- Use the same AWS account ID and attach the IAM policy shown below.

- Trust relationship JSON:


{
 "Version": "2012-10-17",
 "Statement": [
   {
     "Effect": "Allow",
     "Action": "sts:AssumeRole",
     "Principal": {
       "AWS": "arn:aws:iam::700893709242:role/optumInsight"
     },
     "Condition": {
       "StringEquals": {
         "sts:ExternalId": "f261b09f-8ed3-11ee-8279-8175da1e454f"
       }
     }
   }
 ]
}

6. IAM Policy Document
Attach the following IAM policy to the above-created role:

Policy JSON as previously specified in Attachment.

7. Verification
Verify deployment success:

- Check Deployment Summary tab in Splunk Data Manager.

- Confirm status is 'Deployed' and green for all sources.

- Validate data ingestion via Splunk Search and CloudWatch logs.

8. Editing AWS Inputs
To adjust existing data inputs:

- In Data Manager, select the AWS input.

- Modify Role, Region, or data type selections as needed.

- Save changes to redeploy CloudFormation stack.

9. Troubleshooting
- For CloudFormation failures: delete and retry.

- Confirm IAM permissions and trust relationships.

- Use Splunk and CloudWatch logs for further diagnostics.