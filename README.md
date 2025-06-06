Here is a detailed, step-by-step breakdown of how VeriMove is used in the NCOA/MACS address validation and standardization process, based on your transcripts:

⸻

🔧 VeriMove Detailed Workflow

VeriMove is a third-party address processing tool that uses USPS NCOA Link data to validate, standardize, and detect moved addresses. The tool is used interactively (via GUI), but can also be configured for automation.

⸻

🟡 Step 1: Launch VeriMove and Configure a Job
	•	Open the VeriMove Application UI on the processing server (typically PROD).
	•	Create or reuse a job definition:
	•	Jobs are designed via VeriMove’s built-in GUI.
	•	Each job corresponds to one input/output configuration (e.g., for a club or use case).

In the Job Configuration:
	•	Define Input Files:
	•	Typically, a MACS file exported from Teradata.
	•	File contains addresses to be validated.
	•	Define NCOA Reference Files:
	•	Point to the monthly USPS NCOA ZIP data folder (already unzipped).
	•	Also reference the “daily delete” file (USPS requirement).
	•	Define Output Files:
	•	You can configure a single output with all records or split into “matched” and “unmatched”.
	•	Currently, only one file is produced with both types.

⸻

🟡 Step 2: Define Field Mappings & Rules

Within the job:
	•	Field Mapping:
	•	Match input file fields (e.g., name, address, ZIP) to USPS-required format.
	•	Optionally, append original fields for later comparison.
	•	Select Output Fields:
	•	Include USPS-provided metadata like:
	•	DPV Footnote Code
	•	NCOA Move Type
	•	Move Date
	•	Forwarding Indicator
	•	Standardized Address fields (e.g., ZIP+4, formatted street address)
	•	Job Settings:
	•	You may define move types to accept (e.g., only 18-month or 48-month moves).
	•	Define paths for logs and error handling.

⸻

🟡 Step 3: Run the VeriMove Job
	•	Execute the job via the GUI (or .EXE file if exported).
	•	VeriMove processes each record:
	•	Matches it against USPS NCOA records.
	•	Returns one of the following:
	•	Moved Address (based on Forwarding Indicator = Y)
	•	Standardized Address (address corrected without a move)
	•	Bad Address (invalid or unmailable)
	•	VeriMove Appends Metadata:
	•	Output file contains original input fields and appended USPS metadata fields.

⸻

🟡 Step 4: Post-Processing Logic

Once VeriMove produces the output file:
	•	Compare Input vs. Output Records:
	•	To detect:
	•	Which records moved (Forwarding Indicator = Y)
	•	Which records were standardized (compare old vs. new address)
	•	Which records are bad (based on DPV Footnote Code)
	•	Classify Records:
	•	Good (mailable)
	•	Bad (unmailable)
	•	Moved (with updated address)
	•	Standardized (same address, USPS-corrected)

⸻

🟡 Step 5: Load Output into Teradata
	•	Use FastLoad to push the entire VeriMove output file into a staging table.
	•	A script classifies rows into:
	•	GOOD_ADDRESS_TABLE
	•	BAD_ADDRESS_TABLE
	•	DPV Codes like M1, M3, N1, P1, R1 are used to flag bad addresses.
	•	Forwarding Indicator is used to flag moved addresses.
	•	Manual or programmatic comparison is required to detect standardized (format-changed) addresses.

⸻

🟡 Step 6: Downstream Actions
	•	Marketing teams use GOOD_ADDRESS_TABLE for direct mail campaigns.
	•	Customer teams may use BAD_ADDRESS_TABLE to call or clean invalid contacts.
	•	Updates are sent back to the MACS master table.
	•	Currently, all records are overwritten.
	•	Plan: Only update moved/standardized ones in the future.

⸻

🔍 Key VeriMove Output Fields

Field	Purpose
DPV Footnote Code	Indicates if address is good/bad
Forwarding Indicator	Y = moved, N = not moved
New Address Fields	If moved, shows new address
Standardized Address	If not moved, corrected format
Move Effective Date	Date USPS recognized the move


⸻

⚠️ Notes & Considerations
	•	Standardized addresses are not flagged explicitly – you must compare fields manually.
	•	Automation of job execution is possible by exporting .exe and running via CLI (needs verification).
	•	VeriMove is mandatory due to USPS licensing – you cannot process NCOA files without it.
	•	No dev/test environment exists for USPS file handling – all work is done in PROD.

⸻

Would you like a visual diagram or PowerPoint version of these steps?