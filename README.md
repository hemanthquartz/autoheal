Here’s a summarized description of the provided architecture:

Architecture Summary

The architecture showcases a file-based ingestion and event-driven processing pipeline consisting of two main patterns: Data Ingestion (Event Driven) and Data Processing Layer (Intraday Batches). Both these layers are monitored and triggered through Control-M, with metadata management centralized through Collibra as a unified governance platform.

Data Ingestion Layer (Event Driven Pattern)
	•	Data Ingestion: Files arrive at a staging area.
	•	Metadata Extraction: AWS Lambda extracts metadata from incoming files.
	•	Event Notification: Metadata extraction triggers events published to Amazon SQS.
	•	Standardization and Synchronization: AWS Step Functions orchestrate file standardization and synchronization activities.
	•	Cataloging and Storage: Standardized files are stored in a Glue Data Catalog, leveraging Apache Iceberg for managing the data lake.

Data Processing Layer (Intraday Batches)
	•	Dynamic Configuration: Job configuration details stored in DynamoDB.
	•	Job Invocation: AWS Lambda fetches job configurations dynamically from DynamoDB.
	•	Orchestration: AWS Step Functions invoke EMR on EKS pods, providing job configuration details dynamically fetched by the Lambda.
	•	Data Catalog and Storage: Processed data gets cataloged via AWS Glue Data Catalog, accessible through Glue JDBC endpoints.
	•	Databases: Results stored in relational databases, maintaining Base and Master data.

Unified Data Governance Platform
	•	Collibra serves as a centralized platform for:
	•	Data Catalog
	•	Data Governance
	•	Data Lineage
	•	Data Quality & Observability

The architecture emphasizes automation, dynamic configuration, event-driven processing, and robust data governance to ensure high-quality data ingestion and batch processing.