Here’s the summary of the architecture organized into two clear categories:

⸻

✅ Ingestion Pattern – Event Driven Architecture
	•	Staging Layer: Initial storage area where raw data lands.
	•	Event Detection: Events triggered upon new data arrival.
	•	Amazon SQS: Message queue for decoupling producer and consumer.
	•	Lambda (Data Synchronization):
	•	Picks messages from SQS.
	•	Triggers Glue Iceberg ingestion.
	•	Glue Iceberg REST Endpoint: Interface for writing to Iceberg tables.
	•	Data Lake: Stores raw and curated data.
	•	Glue Data Catalog: Updates metadata for discoverability.
	•	Control-M (Monitoring): Monitors ingestion flows and events.

⸻

⚙️ Processing Pattern – Intraday Batch Architecture
	•	Step Function: Orchestrates batch processing steps.
	•	Lambda (Job Invocation): Initiates EMR job based on configurations.
	•	EMR on EC2: Executes Spark jobs or batch transformations.
	•	Outputs Written to:
	•	Base Layer
	•	Master Layer
	•	Glue Data Catalog: Updates metadata for processed datasets.
	•	Control-M (Triggering): Initiates processing jobs on schedule or condition.

⸻

🔐 Unified Governance Layer (Supports Both Patterns)
	•	Collibra Platform:
	•	Data Catalog
	•	Data Governance
	•	Data Lineage
	•	Data Quality & Observability

⸻

Let me know if you’d like a diagrammatic breakdown or editable version for documentation or presentation.