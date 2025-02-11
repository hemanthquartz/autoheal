import os
import subprocess
import json
import uuid
import yaml
from openai import AzureOpenAI
from github import Github

# Azure OpenAI Credentials
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")
API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
RESOURCE_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

# GitHub Credentials
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME_SECRET", "")  # Ensure REPO_NAME is set
BRANCH_NAME = f"autoheal-fix-{uuid.uuid4().hex[:8]}"

def get_terraform_error():
    """Reads Terraform apply error from the GitHub Actions log file."""
    log_path = "terraform/tf_error_log.txt"
    try:
        with open(log_path, "r") as log_file:
            error_log = log_file.read().strip()
        
        if error_log and "Error" in error_log:
            return error_log
        else:
            return "No error detected"
    except Exception as e:
        return str(e)

def get_openai_fix(error_message, original_code):
    """Send Terraform error to Azure OpenAI and get the fixed code."""
    client = AzureOpenAI(
        api_version=API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY
    )

    # Providing more context and asking only for corrected Terraform code
    prompt = f"""
    I have a configuration file that failed during deployment. 
    Below is the error log:
    ---
    {error_message}
    ---
    Here is the current file content:
    ---
    {original_code}
    ---
    Please provide only the corrected file content as output, keeping everything else unchanged.
    Do not include explanations or descriptions, only return the modified file in the correct format.
    Ensure the output is a well-formatted file based on its type (Terraform, YAML, JSON, etc.).
    """

    response = client.chat.completions.create(
        model=RESOURCE_NAME,
        messages=[
            {"role": "system", "content": "You are a configuration management expert, skilled in Terraform, YAML, and JSON."},
            {"role": "user", "content": prompt}
        ]
    )

    # Extract only the code block (assuming OpenAI formats it within triple backticks)
    response_text = response.choices[0].message.content.strip()
    if "```" in response_text:
        return response_text.split("```")[1].strip()
    return response_text

def format_file_content(file_path, content):
    """Format the modified file content based on file type."""
    if file_path.endswith(".yaml") or file_path.endswith(".yml"):
        try:
            parsed_yaml = yaml.safe_load(content)  # Validate YAML format
            return yaml.dump(parsed_yaml, default_flow_style=False)  # Pretty print YAML
        except yaml.YAMLError as e:
            print(f"Warning: YAML formatting failed: {e}")
            return content  # Return original content if formatting fails

    elif file_path.endswith(".json"):
        try:
            parsed_json = json.loads(content)  # Validate JSON format
            return json.dumps(parsed_json, indent=4)  # Pretty print JSON
        except json.JSONDecodeError as e:
            print(f"Warning: JSON formatting failed: {e}")
            return content  # Return original content if formatting fails

    return content  # Return as-is for other file types

def update_modified_file(fixed_code, file_path):
    """Ensure only the relevant lines are modified while keeping everything else the same and formatted correctly."""

    # Read existing file content
    with open(file_path, "r") as file:
        original_content = file.readlines()

    # Convert fixed_code into a dictionary mapping keys to values
    modified_lines = fixed_code.strip().split("\n")
    modified_map = {}
    for line in modified_lines:
        if "=" in line or ":" in line:  # Handle both Terraform and YAML/JSON formats
            key = line.split("=")[0].strip() if "=" in line else line.split(":")[0].strip()
            modified_map[key] = line.strip()

    # Replace only the modified parts while keeping everything else unchanged
    updated_content = []
    for line in original_content:
        stripped_line = line.strip()
        if "=" in stripped_line or ":" in stripped_line:
            key = stripped_line.split("=")[0].strip() if "=" in stripped_line else stripped_line.split(":")[0].strip()
            if key in modified_map:
                line = modified_map[key] + "\n"  # Replace the line only if modified
                del modified_map[key]  # Ensure no duplicates
        updated_content.append(line)

    # Ensure correct formatting based on file type
    formatted_content = format_file_content(file_path, "".join(updated_content))

    # Write back the updated content
    with open(file_path, "w") as file:
        file.write(formatted_content)

def create_github_pr(file_path):
    """Create a new Git branch, commit the fix, and open a PR."""
    g = Github(GITHUB_TOKEN)
    if not REPO_NAME:
        print("Error: REPO_NAME_SECRET environment variable is missing. Ensure it is set in GitHub Actions secrets.")
        return

    repo = g.get_repo(REPO_NAME)
    
    # Create a new branch
    main_ref = repo.get_git_ref("heads/main")
    try:
        repo.create_git_ref(ref=f"refs/heads/{BRANCH_NAME}", sha=main_ref.object.sha)
    except Exception as e:
        if 'Reference already exists' in str(e):
            print(f"Branch {BRANCH_NAME} already exists. Proceeding with commit and PR.")
        else:
            print(f"Error creating branch: {e}. Ensure the GitHub token has 'contents: write' permissions.")
            return

    # Commit changes
    with open(file_path, "r") as file:
        content = file.read()
    repo.get_contents(file_path, ref=BRANCH_NAME)
    repo.update_file(file_path, "AutoHeal: Fix Configuration Error", content, repo.get_contents(file_path, ref=BRANCH_NAME).sha, branch=BRANCH_NAME)
    
    # Create PR
    try:
        repo.create_pull(title="AutoHeal: Fix Deployment Configuration Error", body="Fixes applied using Azure OpenAI.", head=BRANCH_NAME, base="main")
    except Exception as e:
        if 'Resource not accessible by integration' in str(e):
            print("Error: GitHub token lacks permission to create PRs. Use a Personal Access Token (PAT) with 'Contents: Write' and 'Pull Requests: Write' permissions.")
        else:
            print(f"Error creating PR: {e}")
        return

def main():
    """Main execution flow."""
    error_log = get_terraform_error()
    if error_log != "No error detected":
        print(f"Deployment error detected:\n{error_log}")
        
        # Identify which file caused the error (assume Terraform file for now)
        modified_file_path = "terraform/main.tf"

        # Read existing file content
        with open(modified_file_path, "r") as file:
            original_code = file.read()

        fix = get_openai_fix(error_log, original_code)
        update_modified_file(fix, modified_file_path)
        create_github_pr(modified_file_path)
    else:
        print("No deployment errors detected.")

if __name__ == "__main__":
    main()
