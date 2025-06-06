
🔁 Monthly NCOA Processing Overview
🟨 1. USPS NCOA File Acquisition
Schedule: Process runs monthly, typically on the 3rd or 4th of each month (even if weekend).

Manual Download:

Log into USPS secure network.

Download the monthly ZIP file (~1–2 GB).

Also download the daily delete file (even though it’s used only monthly).

Unzipping:

Unzip into a predefined USPS folder on the same prod server (e.g., D:\USPS\data\).

Output includes many hashed data files.

File names appear static and are overwritten every month.

Compliance Note:

Development work should not occur on raw USPS data.

Files are retained through the month but overwritten next cycle.

USPS requires the use of a third-party tool (VeriMove); direct scripting against USPS data is contractually restricted.

🟨 2. MACS and Magazine Files Acquisition
Magazine Files:

Created by AAA’s mainframe membership system on the 3rd of each month.

Auto-FTP’d to the processing server.

Each file corresponds to one of the 9 clubs (no club code in file = can't merge).

MACS (Member Address Correction System) Files:

Pulled manually from Teradata using fast export.

Kevin or equivalent executes the export using prebuilt .bteq or .fastexp scripts.

Dumped to the server in a specific folder as flat files.

🟨 3. VeriMove Processing
Setup:

VeriMove UI is used to design jobs per input/output configuration.

Each job takes one input file and defines an output location.

Separate jobs are configured for each of the 9 clubs due to missing club codes.

Execution:

Run manually through the VeriMove UI.

Optionally, export jobs as executables for CLI automation (to be explored).

Inputs:

USPS monthly file

USPS daily delete file

MAX file (customer data)

Outputs:

Combined file with address corrections.

Currently only generating a merged output (match + unmatched).

🟨 4. VeriMove Output Details
The output file mirrors the input record layout with appended USPS-provided fields.

Fields used for analysis:

DPV Footnote Codes:

e.g., M1, M3, N1, P1, R1 = Bad addresses

Other codes = Good/mailable addresses

Forwarding Indicator:

Y = Address has moved

N = No move, possibly standardized

The output file does not explicitly indicate standardized addresses — this must be inferred by comparing original vs. output address.

🟨 5. Comparison & Analysis
Comparison Logic:

Custom scripts compare original MCAS input with VeriMove output.

Determine:

Address moved

Address standardized (e.g., ZIP+4 added, formatting corrected)

Address invalid/bad

Classification:

Good Address: Keep and use for mailing.

Moved Address: Use updated address from USPS.

Standardized Address: Use corrected format.

Bad Address: Segregated into a separate table for review.

DPV codes drive filtering.

🟨 6. Post-Processing & Data Load
Staging Table:

Output of VeriMove is bulk loaded into a staging table in Teradata using fastload.

Scripted Split:

SQL or BTEQ jobs split the staging data into:

GOOD_ADDRESS_TABLE

BAD_ADDRESS_TABLE

Current Practice:

Entire processed file (e.g., all 125M records) is updated into MCAS table monthly.

Planned Optimization:

Only update:

Moved addresses (via forwarding indicator)

Standardized addresses (via manual compare logic)

Leave good/unchanged addresses as-is.

Possibly delete or flag bad addresses.

🟨 7. Final Data Usage
Good Records:

Used for direct mail marketing campaigns.

Bad Records:

Saved for call center outreach or research.

All records are versioned monthly.

Option exists to merge good/bad into one table with flags (IS_MAILABLE, HAS_MOVED, etc.).

🟨 8. Automation Opportunities
File Download:

Currently manual.

Opportunity to automate via USPS APIs or batch script (requires USPS approval/contact).

VeriMove CLI:

Need to explore ability to run VeriMove jobs via CLI/exec files instead of GUI.

Lambda/Glue Integration:

Ideal end-state: AWS Lambda or Glue jobs trigger processing and upload results to S3.

Access Management:

Controlled via project-specific credentials and access requests (e.g., Harman manages for team).

🟨 9. Dev/Test Environment Constraints
USPS provides no Dev or QA data environments.

Only Prod server exists.

All automation/dev must be carefully coordinated to not breach USPS compliance.


