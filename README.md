Perfect — since it’s a demo environment, you can use cost-effective general-purpose EC2 instances for EKS, while still supporting basic Spark workloads.

Here’s the updated and final list with that adjustment:

⸻

✅ Complete List of Services Involved in the Architecture (Demo Environment)

AWS Services
	1.	Amazon S3 – Staging area, data lake zones (Base/Master), logs
	2.	AWS Lambda – Metadata extraction, job config fetcher, and job invoker
	3.	AWS Step Functions – Orchestration of ingestion and processing pipelines
	4.	AWS Glue – File standardization and ETL transformations
	5.	AWS Glue Data Catalog – Schema and metadata management
	6.	Amazon EMR (on EC2) – Spark-based intraday batch processing
	7.	Amazon EKS (on EC2) – Optional container-based Spark job execution
	•	✅ For demo use, cost-effective EC2 instance types for EKS node groups:
	•	t3.large (2 vCPU, 8 GiB RAM)
	•	m5.large (2 vCPU, 8 GiB RAM)
	•	m5.xlarge (4 vCPU, 16 GiB RAM — better for light Spark workloads)
	8.	Amazon CloudWatch – Logs, metrics, alarms, and dashboards
	9.	AWS IAM – Role and policy management across all services
	10.	Amazon EventBridge / S3 Event Notifications – Trigger Step Functions when files land in S3

⸻

CI/CD and IaC Tools
	11.	Jenkins – CI/CD automation for Lambda, Step Functions, EMR job scripts
	12.	GitHub – Source control for code, ETL scripts, and infrastructure templates
	13.	CloudFormation / Terraform – Infrastructure provisioning and configuration management

⸻

Let me know if you want this as a presentation slide (PPTX) or visual diagram.