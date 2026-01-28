- Meeting title: Verimo Setup Options Review
- Participants (as inferred): Speaker 1 (primary presenter), others (questions/comments from Crystal and unnamed speakers); meeting focused on deployment/setup decisions and access controls.

Context and purpose
- Purpose: Decide how to set up Verimo in production and confirm access/roles for emergency troubleshooting.
- Two high-level setup approaches were proposed and compared: manual in-prod setup vs. creating and using an AMI image.

Option A — Manual production setup (described as “prod one” / first option)
- Process:
  - Install Verimo manually on a production Windows box.
  - Run required manual steps to configure and confirm the environment.
  - Execute/verify automation scripts run as expected after manual install.
  - Once fully configured and validated, create an AMI from that manually configured prod instance for future reuse.
- Pros implied:
  - Ensures initial setup is done in prod environment directly.
  - The AMI will reflect an already validated prod configuration.
- Considerations:
  - Manual work upfront each time for initial installs.
  - Need to ensure nothing sensitive or non-prod artifacts are introduced when creating AMI (although this is more explicitly discussed for Option B).

Option B — Create sanitized AMI from pre-prod (image-first approach)
- Process:
  - Use existing non-prod / pre-prod instance which already has Verimo installed and setup steps applied.
  - Remove all data-related artifacts and pre-prod-specific data from that instance (sanitize it).
  - Create an AMI of the sanitized pre-prod instance.
  - Use that AMI to launch prod instances in future.
- Alternative within Option B:
  - Instead of sanitizing pre-prod, first perform a one-time manual prod setup and then create an AMI from that prod instance (this overlaps with Option A’s end state).
- Pros implied:
  - Faster spin-up for future instances using a prepared image.
  - Can standardize and automate builds once AMI is available.
- Risks & controls:
  - Risk of accidentally pushing pre-prod data to production if the pre-prod instance is not fully sanitized.
  - Need to run the AMI creation and transfer through appropriate guardrails/review to ensure no data leakage to prod.
  - Crystal raised questions about feasibility and guardrail checks.

Access, roles, and emergency troubleshooting
- Topic: Confirming a role that grants Don and Kevin permission to log into the Windows box.
- Purpose of role:
  - Not for routine manual steps; intended for worst-case scenarios or emergency troubleshooting (e.g., to check what went wrong, view events).
  - Allows login and monitoring of Verimo process events and relevant system events.
- Current state discussed:
  - A role request has been made (or is planned) to give Don and Kevin access; need confirmation that it exists and is properly configured.
  - The role in pre-prod exists and is being referenced as the model for prod access.

Action items (as recorded in meeting summary, assignee listed as Speaker 0 in transcript summary)
- Decide on the Verimo setup approach and document the chosen approach so the team can proceed (manual prod setup vs. AMI-based approach).
- If choosing AMI from pre-prod:
  - Create an AMI from pre-prod after removing all data artifacts.
  - Perform guardrail/review to ensure no pre-prod data is pushed to prod.
  - Deliver sanitized AMI to production.
- If choosing manual-first:
  - Manually configure the Windows box in production.
  - Create an AMI from that manually configured instance and use it for future launches.
- Confirm that the requested role granting Don and Kevin permission to log into the Windows box exists and that access is configured strictly for emergency troubleshooting and monitoring.

Clarifications and decisions needed (next steps for the team)
- Team must choose between:
  - Manual initial prod setup then AMI creation (Option A), or
  - Sanitize pre-prod and create AMI for prod (Option B).
- Define and document guardrail/review process and responsible party to prevent data leakage from pre-prod to prod.
- Confirm the role creation and specific permissions for Don and Kevin; decide whether role mirrors pre-prod role exactly or needs adjustments for prod.
- Assign owners and deadlines for:
  - AMI creation and sanitization,
  - Guardrail compliance review,
  - Manual prod setup (if chosen),
  - Role configuration and verification for Don and Kevin.

Precise points mentioned in transcript worth noting
- Two options repeated multiple times: manual prod install vs. create AMI.
- Concern about pushing pre-prod data to prod — guardrails/review emphasized.
- The role is explicitly for troubleshooting/worst-case scenarios, not regular manual work.
- Speaker 1 repeatedly asked for confirmation to move forward after addressing these two points.

No verbatim quotes extracted beyond paraphrase (transcript available in meeting context).