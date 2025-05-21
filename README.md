General Migration Questions
	1.	What is the current migration architecture for Hadoop and Teradata to S3?
	•	Are we using AWS DataSync, Glue, DMS, custom scripts, or third-party tools?
	2.	What is the frequency of migration?
	•	One-time, scheduled batch (daily/weekly), or real-time streaming?
	3.	What is the current cutover/migration strategy?
	•	Lift-and-shift, phased migration, or hybrid model?

⸻

Hadoop-Specific Questions
	4.	What tools are being used to move data from Hadoop to S3?
	•	Is it AWS DataSync, DistCp with EMR, or custom Spark/MapReduce jobs?
	5.	Are we preserving file format and structure (e.g., Parquet, ORC) during the move to S3?
	6.	What is the data volume per job and total size?
	•	Confirm the 260 TB mentioned earlier.
	7.	Are there specific AWS S3 storage classes (e.g., Standard, Intelligent-Tiering) being used for different datasets?

⸻

Teradata-Specific Questions
	8.	What tool is being used to extract data from Teradata?
	•	AWS SCT + DMS, custom ETL, Informatica, etc.?
	9.	Is the Teradata schema being replicated as-is in S3 or transformed (e.g., flattened, normalized)?
	10.	What is the volume of Teradata data being migrated (confirm if it’s 160 TB)?
	11.	Are there performance or throttling issues during extract or load phases?

⸻

AWS Environment & Permissions
	12.	What IAM roles and policies are required for this migration?

	•	Any cross-account access or STS roles involved?

	13.	Is there a dedicated VPC, subnet, and endpoint setup for DataSync or Glue/DMS tasks?
	14.	Is CloudWatch or any logging enabled to monitor failures or throughput metrics?

⸻

Validation & Post-Migration
	15.	How is data integrity being validated post-migration?

	•	Hashing, row counts, record-level comparisons?

	16.	Are there downstream consumers (e.g., Athena, Redshift, Lake Formation) that need schema alignment?
	17.	Is versioning or lifecycle policy enabled on the S3 buckets?


Storage Questions (Source & Destination)
	1.	Hadoop:
	•	What is the file system used in the Hadoop cluster (HDFS or cloud-native like S3A)?
	•	Are there any compression formats being used (e.g., Snappy, Gzip)?
	•	What is the average file size and block size configuration?
	2.	Teradata:
	•	Are we extracting from raw tables or views?
	•	Is data partitioned in Teradata for optimized extraction?
	3.	S3:
	•	What bucket configuration is used? (e.g., versioning, encryption, object lock)
	•	Are S3 prefixes structured based on source system/date/entity?
	•	What storage class is used per dataset (Standard, Infrequent Access, Glacier)?
	•	Is AWS Lake Formation being used for data catalog and access control?

⸻

Network Questions
	4.	Source Connectivity:
	•	How is connectivity established from the on-prem Hadoop and Teradata systems to AWS? (Direct Connect, VPN, or public internet?)
	•	Are there any firewalls, proxies, or ACLs that interfere with data movement?
	5.	Throughput & Bandwidth:
	•	What is the current network bandwidth available for migration?
	•	What is the sustained throughput during data transfer (in MB/s or GB/hour)?
	•	Are there known latency spikes or dropped packet issues during transfer?
	6.	Data Movement:
	•	Are we using parallelism for extraction and transfer?
	•	Any network acceleration tools being used (e.g., AWS DataSync, AWS Snowball, S3 Transfer Acceleration)?

⸻

Compute Questions
	7.	ETL/Processing:
	•	Are we using AWS Glue, EMR, or custom EC2 instances for pre/post processing?
	•	What is the compute configuration (vCPUs, memory) used for Glue/EMR jobs?
	•	Are we using spot or on-demand instances?
	8.	Teradata & Hadoop Nodes:
	•	What is the size and type of Hadoop/Teradata cluster (nodes, CPU/memory)?
	•	Is there any compute saturation or I/O bottleneck during extract?

⸻

Operational & Security Questions
	9.	Authentication & Access:
	•	Are we using IAM roles for services, or hardcoded credentials?
	•	Is S3 access restricted using resource policies or bucket policies?
	10.	Logging & Monitoring:

	•	Are we tracking transfer jobs via CloudWatch, AWS Glue job logs, or a custom dashboard?
	•	Is there an alerting mechanism for failed or slow jobs?

	11.	Throttling & Limits:

	•	Are we hitting any API throttling or request limits (S3 PUT, DMS connections, Glue job concurrency)?

⸻

Challenges & Bottlenecks
	12.	What are the biggest pain points you’re currently seeing?

	•	Slow transfer times?
	•	Schema mismatches?
	•	Partial or corrupt file uploads?
	•	Resource contention on source systems?
	•	Data consistency across incremental loads?

	13.	Any past issues with checkpointing, retries, or fault tolerance?
	14.	Any disk space issues on source clusters due to staging data before transfer?
	15.	Are job schedules overlapping or causing load spikes on Teradata or Hadoop?


