Here are the detailed minutes of the Data Migration Strategy Meeting:

Meeting Title: Data Migration Strategy Meeting

Key Discussion Points:
1. Encryption Zone and Key Management
- Need to create an encryption zone on AWS similar to current Hadoop setup
- Use Luna HSM for encryption key management
- Integrate Luna HSM with AWS customer-managed keys
- Secure data access using potential Lake Formation implementation

2. Teradata Migration Strategy
- Modernizing legacy system (over 20 years old)
- Separate processes for AWS and Snowflake
- Focus on Power insurance application data mart migration
- Current data source: Mainframe using Click Replica tool
- Migration timeline: October-November

3. Data Migration Technical Considerations
- Use AWS Schema Conversion Tool (SCT) for data extraction
- Estimated source data volume: 10 terabytes
- Potential use of services like AWS Glue, DMS, Lambda
- Maintain existing data ingestion tools (Click Replica)

4. Key Action Items
- Test AWS Schema Conversion Tool
- Investigate Luna HSM integration with AWS
- Explore Lake Formation for data security
- Attend Power application planning meeting
- Contact technology team for HSM credentials

5. Contact Information
- Technology Team Product Owner: Tharn Lee
- Program Manager for Migration: VEDA
- JIRA Board: DDT Backlog under DNA Tech Enablement

Participants: Mahesh (Speaker 2), Speaker 1 (AWS Expert)

Next Steps: Continued collaboration on migration strategy and technical implementation.