🟨 Stage 1: File Preparation and Setup
Step	Description
1.1	Each month, the latest NCOA ZIP file and daily delete file are manually downloaded from the USPS secure portal. This typically occurs in the first few days of the month.
1.2	These files are then extracted into a designated USPS folder on a production server. The contents of the ZIP file include multiple data components provided by USPS.
1.3	This download step completes the USPS interaction, and the data can now be used for internal processing. The data remains in the folder until the next month's overwrite.
1.4	At the same time, MACS (internal member address) data is exported manually from Teradata using fast export, generating a flat input file for processing.
1.5	Magazine mailing data is also retrieved via automated FTP from a mainframe system. These files are broken down by club, and cannot be merged due to lack of club codes in the original file.

🟨 Stage 2: VeriMove Address Matching and Enrichment
Step	Description
2.1	The VeriMove application is launched on the server, and users select or configure jobs using its GUI interface.
2.2	For each job, the user defines the input file (MACS data), the USPS NCOA directory path, and the daily delete file. These are mapped through VeriMove's setup screens.
2.3	Field mapping is done to align the input structure (name, address, city, ZIP, etc.) with USPS-required fields.
2.4	The user then configures the job to produce enriched output fields, such as USPS DPV (Delivery Point Validation) codes, move flags, and standardized address suggestions.
2.5	The job is run manually through the GUI, and VeriMove processes the records using USPS data. The output contains the original input along with enriched fields, all in a single file.
2.6	Although VeriMove supports splitting into matched/unmatched files, the current setup uses a unified output. Executable versions of jobs can be saved for potential CLI automation, though this isn’t widely used yet.

🟨 Stage 3: Output Comparison and Record Classification
Step	Description
3.1	The enriched output file from VeriMove is loaded into a staging table in Teradata using the fastload utility.
3.2	Custom scripts and comparison logic are used to analyze each record and classify them into four categories: moved, standardized, bad, and unchanged.
3.3	Records with a forwarding indicator of 'Y' are treated as moved. Their new address details are extracted and flagged for update.
3.4	Records with a forwarding indicator of 'N' but with differences between original and output address fields are considered standardized. These represent formatting or ZIP+4 corrections.
3.5	Records with specific USPS DPV footnote codes (such as M1, M3, N1, etc.) are deemed unmailable or invalid. These are categorized as bad addresses.
3.6	Records with no forwarding and no address change, and that pass USPS validation, are treated as valid and unchanged.

🟨 Stage 4: Database Update and Segregation
Step	Description
4.1	All records from the staging table are processed. Moved and standardized addresses are updated in the MACS master table.
4.2	Good addresses are stored and reused for mailing purposes, such as for AAA magazine dispatch.
4.3	Bad addresses are segregated into a dedicated table. These may later be used for call campaigns or internal audits.
4.4	While currently all records are re-uploaded to MACS monthly, a future-state goal is to update only the changed addresses (moved or standardized) and exclude unchanged ones.

🟨 Stage 5: Monthly Execution and Retention
Step	Description
5.1	The process is run monthly, typically starting on the 3rd or 4th of the month. This timeline aligns with availability of magazine and USPS files.
5.2	If these dates fall on a weekend, the process is still executed to maintain continuity.
5.3	Previous USPS files are overwritten with the new cycle's files; no versioning is currently maintained.
5.4	The monthly MACS table is refreshed with the processed data so it can be used for comparison in the next month’s cycle.

🟨 Stage 6: Classification Logic Summary
Classification	Criteria
Moved	Forwarding indicator = 'Y'. Indicates the person has moved and USPS provided a new address.
Standardized	Forwarding indicator = 'N' and address fields differ. Address corrected in format or ZIP+4.
Bad	USPS DPV code in known invalid values (M1, M3, N1, etc.). Unmailable address.
Valid/Unchanged	No move, no address change, and USPS validation passes. No action required.

🟨 Stage 7: Automation and Compliance Considerations
Step	Description
7.1	All download and processing steps are currently manual. There is interest in automating these, starting with USPS downloads and VeriMove executions.
7.2	The USPS contract mandates using approved third-party tools (like VeriMove) and restricts direct manipulation of USPS data files.
7.3	Any automation must remain compliant with USPS regulations. External contact with USPS is needed to explore API access for automation.
