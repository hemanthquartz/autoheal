import os
import subprocess
import json
import uuid
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
    """Send Terraform error to Azure OpenAI and get the fixed Terraform code only."""
    client = AzureOpenAI(
        api_version=API_VERSION,
        azure_endpoint=AZURE_ENDPOINT,
        api_key=API_KEY
    )

    # Providing more context and asking only for corrected Terraform code
    prompt = f"""
    I have a Terraform configuration that failed during deployment. 
    Below is the Terraform error log:
    ---
    {error_message}
    ---
    Here is the current Terraform code:
    ---
    {original_code}
    ---
    Please provide only the corrected Terraform code as output, keeping everything else unchanged.
    Do not include explanations or descriptions, only return the modified code block.
    Ensure the output does not have duplicate lines and all other source lines remain unchanged.
    """

    response = client.chat.completions.create(
        model=RESOURCE_NAME,
        messages=[
            {"role": "system", "content": "You are a Terraform expert specializing in fixing deployment issues."},
            {"role": "user", "content": prompt}
        ]
    )

    # Extract only the code block (assuming OpenAI formats it within triple backticks)
    response_text = response.choices[0].message.content.strip()
    if "```" in response_text:
        return response_text.split("```")[1].strip()
    return response_text

def update_main_tf(fixed_code):
    """Ensure only the relevant lines are modified while keeping everything else the same and avoiding duplicates."""
    tf_path = "terraform/main.tf"

    # Read existing main.tf content
    with open(tf_path, "r") as file:
        original_content = file.readlines()

    # Convert fixed_code into a dictionary mapping keys to values
    modified_lines = fixed_code.strip().split("\n")
    modified_map = {}
    for line in modified_lines:
        if "=" in line:
            key = line.split("=")[0].strip()
            modified_map[key] = line.strip()

    # Replace only the modified parts while keeping everything else unchanged
    updated_content = []
    for line in original_content:
        stripped_line = line.strip()
        if "=" in stripped_line:
            key = stripped_line.split("=")[0].strip()
            if key in modified_map:
                line = modified_map[key] + "\n"  # Replace the line only if modified
                del modified_map[key]  # Ensure no duplicates
        updated_content.append(line)

    # Write back the updated content
    with open(tf_path, "w") as file:
        file.writelines(updated_content)

def create_github_pr():
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
    file_path = "terraform/main.tf"
    with open(file_path, "r") as file:
        content = file.read()
    repo.get_contents(file_path, ref=BRANCH_NAME)
    repo.update_file(file_path, "AutoHeal: Fix Terraform error", content, repo.get_contents(file_path, ref=BRANCH_NAME).sha, branch=BRANCH_NAME)
    
    # Create PR
    try:
        repo.create_pull(title="AutoHeal: Fix Terraform Deployment Error", body="Fixes applied using Azure OpenAI.", head=BRANCH_NAME, base="main")
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
        print(f"Terraform error detected:\n{error_log}")
        
        # Read existing Terraform code
        tf_path = "terraform/main.tf"
        with open(tf_path, "r") as file:
            original_code = file.read()

        fix = get_openai_fix(error_log, original_code)
        update_main_tf(fix)
        create_github_pr()
    else:
        print("No Terraform errors detected.")

if __name__ == "__main__":
    main()
